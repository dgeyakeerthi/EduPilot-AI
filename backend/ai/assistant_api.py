"""Authenticated, bounded tool-calling API for EduPilot AI.

The LLM may propose only one of the six registered capabilities. Every handler
is closed over the authenticated student id; model arguments can never choose
another user's id. Eligibility remains deterministic and submission is absent.
"""
from __future__ import annotations
import json, re, uuid
from pathlib import Path
from fastapi import Depends
from pydantic import BaseModel, Field
from backend.ai.orchestrator import build_registry, MAX_TOOL_CALLS
from backend.ai import router
from backend.ai.rag import retrieve_student_documents

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=3000)
    conversation_id: str | None = Field(default=None, max_length=80)

SPECIALISTS = {
    "discovery": "Scholarship discovery specialist: find and explain scholarship records and official sources.",
    "profile_documents": "Student profile and document specialist: inspect only the authenticated student’s own saved profile and document metadata.",
    "eligibility": "Eligibility specialist: request deterministic backend evaluation; never calculate or decide eligibility yourself.",
    "applications": "Application preparation specialist: create drafts only; never submit or approve on behalf of the student.",
    "tracking": "Application tracking specialist: retrieve only the authenticated student’s own recorded status and timeline.",
    "general": "General scholarship guidance specialist: answer cautiously and state when official information is unavailable.",
}

ALLOWED = {
    "scholarship_search": {"query"},
    "profile_lookup": set(),
    "document_lookup": set(),
    "eligibility_evaluation": {"scholarship_id"},
    "application_preparation": {"scholarship_id"},
    "tracking_retrieval": {"application_id"},
}

def _json_object(text: str):
    if not text: return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else None
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match: return None
        try: return json.loads(match.group(0))
        except Exception: return None

def setup(app, user, db, err, now, scholarships, eligibility):
    def owned_user(uid):
        row = db().execute("SELECT * FROM students WHERE id=?", (uid,)).fetchone()
        if not row: raise ValueError("Authenticated student no longer exists")
        return row

    def make_tools(uid):
        def search(query=""):
            q = str(query).lower().strip()[:120]
            found = [s for s in scholarships if not q or q in (s.get("scholarship_name","")+" "+s.get("description","")+" "+s.get("provider_name","")).lower()]
            return [{k:s.get(k) for k in ("scholarship_id","scholarship_name","provider_name","description","closing_date","verification_status","official_source_url")} for s in found[:8]]
        def profile():
            p = json.loads(owned_user(uid)["profile"])
            # Minimise cloud exposure: no income, category, DOB, phone, address or identity numbers. Deterministic eligibility evaluates sensitive fields inside the backend.
            keys = ("education_level","course_name","course_year","institution_name","institution_type","academic_score_type","academic_year","preferred_language","state")
            return {k:p.get(k) for k in keys if p.get(k) is not None}
        def documents():
            c = db()
            try: rows = c.execute("SELECT data FROM documents WHERE student_id=?", (uid,)).fetchall()
            except Exception: return []
            out=[]
            for row in rows:
                d=json.loads(row["data"])
                out.append({k:d.get(k) for k in ("document_id","id","document_type","file_name","filename","extraction_status","uploaded_at","status") if d.get(k) is not None})
            return out[:30]
        def get_s(sid):
            s=next((x for x in scholarships if x.get("scholarship_id")==sid),None)
            if not s: raise ValueError("Scholarship not found")
            return s
        def evaluate(scholarship_id):
            return eligibility.assess(get_s(scholarship_id), json.loads(owned_user(uid)["profile"]))
        def prepare(scholarship_id):
            s=get_s(scholarship_id)
            if eligibility.status(s) != "Open": return {"created":False,"reason":"Scholarship is not currently open."}
            c=db(); aid=str(uuid.uuid4()); p=json.loads(owned_user(uid)["profile"])
            fields={k:{"value":p.get(k),"source":"profile"} for k in ("full_name","course_name","education_level","institution_name","state") if p.get(k)}
            missing=list(s.get("required_documents",[]))
            data={"form_fields":fields,"answers":{},"documents_confirmed":[],"missing_documents":missing}
            timeline=[{"event":"Draft created by authenticated AI assistance","event_source":"AI_Assistance","verification_status":"Unverified","recorded_at":now()}]
            c.execute("INSERT INTO applications(id,student_id,scholarship_id,status,data,timeline) VALUES(?,?,?,?,?,?)",(aid,uid,scholarship_id,"Draft",json.dumps(data),json.dumps(timeline))); c.commit()
            return {"created":True,"application_id":aid,"application_status":"Draft","missing_documents":missing,"note":"Draft only; student review and explicit approval are required. This tool cannot submit."}
        def tracking(application_id):
            r=db().execute("SELECT * FROM applications WHERE id=? AND student_id=?",(application_id,uid)).fetchone()
            if not r: return {"found":False,"message":"Application not found for this student."}
            return {"found":True,"application_id":r["id"],"scholarship_id":r["scholarship_id"],"application_status":r["status"],"timeline":json.loads(r["timeline"])}
        return build_registry(scholarship_search=search,profile_lookup=profile,document_lookup=documents,
            eligibility_evaluate=evaluate,application_prepare=prepare,tracking_retrieve=tracking)

    @app.post("/api/assistant/chat")
    def chat(body: ChatRequest, u=Depends(user)):
        if u["role"] != "student": raise err("forbidden","Student assistant access required",403)
        uid=u["id"]; cid=body.conversation_id or str(uuid.uuid4())
        c=db(); c.execute("CREATE TABLE IF NOT EXISTS assistant_messages(id TEXT PRIMARY KEY,student_id TEXT,conversation_id TEXT,role TEXT,content TEXT,created_at TEXT)")
        history=c.execute("SELECT role,content FROM assistant_messages WHERE student_id=? AND conversation_id=? ORDER BY created_at DESC LIMIT 8",(uid,cid)).fetchall()
        history=list(reversed(history))
        registry=make_tools(uid); state={"calls":0}; results=[]
        # Student-owned document RAG is retrieved locally. Document excerpts are never sent to Gemini.
        document_rag=retrieve_student_documents(db, uid, body.message, top_k=4)
        manifest=registry.manifest()
        planner=("You are EduPilot AI. Decide which registered tools are needed. Return ONLY JSON with keys agent, tool_calls and answer. agent must be one of: discovery, profile_documents, eligibility, applications, tracking, general. "
          "tool_calls must be an array of at most 5 objects {name,arguments}; answer is a brief string. "
          "Use only these exact tool names and argument keys. Do not invent results. If tools are unnecessary, return no calls and answer directly only for general guidance. "
          "Never guarantee eligibility, selection, authenticity, approval, submission or payment. Do not ask for passwords, OTPs, CAPTCHA, bank credentials or full identity numbers. "
          "Application preparation creates a draft only; never submit. Eligibility must be read from deterministic tool output.\nTOOLS="+json.dumps(manifest)+
          "\nRECENT HISTORY="+json.dumps([dict(x) for x in history])+
          "\nUSER QUESTION="+body.message)
        planned=router.complete(planner,light=False,task="assistant_tool_planning")
        plan=_json_object(planned.get("text")) if planned.get("provider")!="none" else None
        if plan:
            calls=plan.get("tool_calls",[])
            if not isinstance(calls,list): calls=[]
            for call in calls[:MAX_TOOL_CALLS]:
                if not isinstance(call,dict): continue
                name=call.get("name"); args=call.get("arguments",{})
                if name not in ALLOWED or not isinstance(args,dict) or set(args)-ALLOWED[name]:
                    results.append({"tool":name,"error":"Rejected invalid or unregistered tool arguments."}); continue
                try:
                    value=registry.call(name,args,state)
                    results.append({"tool":name,"result":value})
                except Exception as exc:
                    results.append({"tool":name,"error":str(exc)[:300]})
        # Synthesis receives only the authenticated student's scoped tool outputs.
        agent_name=plan.get("agent", "general") if plan else "general"
        if agent_name not in SPECIALISTS: agent_name="general"
        synthesis=("You are now handing the task to the selected EduPilot specialist. "+SPECIALISTS[agent_name]+"\n"
          +"Answer the student's question using these tool results only for personal/application facts. "
          "If results are missing or errors occurred, state the limitation. Cite official_source_url values when present. "
          "Do not infer authenticity or official eligibility. Never say an application was submitted.\nQUESTION="+body.message+
          "\nTOOL_RESULTS="+json.dumps(results,default=str)[:14000]+
          "\nSTUDENT_DOCUMENT_EXCERPTS (private; use only if relevant; quote source filename):="+json.dumps(document_rag["excerpts"],ensure_ascii=False)[:7000]+
          "\nSPECIALIST="+agent_name+"\nDRAFT_ANSWER="+(str(plan.get("answer","")) if plan else ""))
        has_private_docs = bool(document_rag.get("excerpts"))
        # If private document text is present, force local Ollama so no personal document content reaches Gemini.
        final=router.complete(synthesis,light=False,task="assistant_response",local_only=has_private_docs) if (plan and results) or has_private_docs else planned
        answer=final.get("text") if final.get("provider")!="none" else None
        if not answer and plan: answer=str(plan.get("answer") or "I couldn't complete that request with the available services. Please use the relevant dashboard page or try again.")
        if not answer:
            # Safe deterministic response when all LLM providers are unavailable.
            answer="AI providers are unavailable right now. Your saved profile, scholarship search and deterministic eligibility tools remain available in the dashboard."
        refs=[]
        def collect(x):
            if isinstance(x,dict):
                for k,v in x.items():
                    if k in ("official_source_url","source_references"):
                        if isinstance(v,str): refs.append(v)
                        elif isinstance(v,list): refs.extend(z for z in v if isinstance(z,str))
                    else: collect(v)
            elif isinstance(x,list):
                for v in x: collect(v)
        collect(results); refs=list(dict.fromkeys(refs))[:10]
        stamp=now()
        c.execute("INSERT INTO assistant_messages VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),uid,cid,"user",body.message,stamp))
        c.execute("INSERT INTO assistant_messages VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),uid,cid,"assistant",answer,stamp)); c.commit()
        return {"conversation_id":cid,"answer":answer,"provider":final.get("provider",planned.get("provider","none")),
                "tool_calls_used":state["calls"],"tool_call_limit":MAX_TOOL_CALLS,"specialist":agent_name,"tool_results":results,"source_references":refs,
                "document_retrieval":{"method":document_rag["method"],"sources":document_rag["sources"]}}

    @app.get("/api/assistant/conversations/{conversation_id}")
    def conversation(conversation_id: str, u=Depends(user)):
        c=db(); c.execute("CREATE TABLE IF NOT EXISTS assistant_messages(id TEXT PRIMARY KEY,student_id TEXT,conversation_id TEXT,role TEXT,content TEXT,created_at TEXT)")
        rows=c.execute("SELECT role,content,created_at FROM assistant_messages WHERE student_id=? AND conversation_id=? ORDER BY created_at",(u["id"],conversation_id)).fetchall()
        return {"conversation_id":conversation_id,"messages":[dict(r) for r in rows]}

    @app.get("/api/assistant/provider-status")
    def provider_status(u=Depends(user)):
        from backend.ai.router import configuration
        return {**configuration(), "document_rag":"student-scoped local-first retrieval",
                "private_document_cloud_policy":"document excerpts are not sent to Gemini"}
