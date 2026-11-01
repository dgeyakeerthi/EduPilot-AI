from dotenv import load_dotenv

load_dotenv()

import os, json, uuid, hmac, hashlib, secrets, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal
from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from backend.services import eligibility as el
from backend.integrations import mailer
from backend.documents import service as docs

AUTH_SECRET = os.environ.get("AUTH_SECRET")
if not AUTH_SECRET:
    raise RuntimeError("Setup error: AUTH_SECRET is not set. Copy .env.example and set a long random value.")
DB_PATH = os.environ.get("DATABASE_URL", "sqlite:///edupilot.db").removeprefix("sqlite:///")
DEMO = os.environ.get("EDUPILOT_DEMO_MODE", "false").lower() == "true"
ROOT = Path(__file__).resolve().parent.parent
SCHOLARSHIPS = json.loads((ROOT / "backend/sample_data/scholarships.json").read_text())

def db():
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row
    c.executescript("""CREATE TABLE IF NOT EXISTS students(id TEXT PRIMARY KEY,email TEXT UNIQUE,pw TEXT,salt TEXT,
      role TEXT DEFAULT 'student',email_verified INT DEFAULT 0,vcode TEXT,profile TEXT DEFAULT '{}',created_at TEXT);
      CREATE TABLE IF NOT EXISTS sessions(th TEXT PRIMARY KEY,student_id TEXT);
      CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY,student_id TEXT,scholarship_id TEXT,status TEXT,
      data TEXT,approved INT DEFAULT 0,timeline TEXT DEFAULT '[]');
      CREATE TABLE IF NOT EXISTS student_documents(
      id TEXT PRIMARY KEY, student_id TEXT NOT NULL, original_name TEXT NOT NULL,
      stored_name TEXT NOT NULL, mime_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
      sha256 TEXT NOT NULL, extraction_text TEXT NOT NULL DEFAULT '', extraction_method TEXT NOT NULL,
      extraction_status TEXT NOT NULL, confidence REAL, page_count INTEGER NOT NULL DEFAULT 0,
      warnings TEXT NOT NULL DEFAULT '[]', extracted_fields TEXT NOT NULL DEFAULT '{}',
      corrected_fields TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
      FOREIGN KEY(student_id) REFERENCES students(id));""")
    return c

app = FastAPI(title="EduPilot AI")
now = lambda: datetime.now(timezone.utc).isoformat()
hp = lambda pw, salt: hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
th = lambda t: hmac.new(AUTH_SECRET.encode(), t.encode(), "sha256").hexdigest()

def err(code, message, status=400, details=None):
    return HTTPException(status, detail={"code": code, "message": message, "details": details or {}})

@app.exception_handler(HTTPException)
async def _h(req, e):
    d = e.detail if isinstance(e.detail, dict) else {"code": "error", "message": str(e.detail), "details": {}}
    return JSONResponse({"error": d, "request_id": str(uuid.uuid4())}, e.status_code)

@app.exception_handler(RequestValidationError)
async def _v(req, e):
    return JSONResponse({"error": {"code": "validation_error", "message": "Invalid input",
        "details": {"fields": [{"loc": list(x["loc"]), "msg": x["msg"]} for x in e.errors()]}}, "request_id": str(uuid.uuid4())}, 422)

def user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise err("unauthenticated", "Login required", 401)
    r = db().execute("SELECT s.* FROM sessions x JOIN students s ON s.id=x.student_id WHERE x.th=?", (th(authorization[7:]),)).fetchone()
    if not r: raise err("unauthenticated", "Invalid or expired session", 401)
    return r

class Reg(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=150)
class Login(BaseModel): email: str; password: str
class Verify(BaseModel): email: str; code: str

@app.get("/api/health")
def health(): return {"status": "ok", "demo_mode": DEMO, "ai": {"gemini": "not_configured", "local_fallback": "not_configured"}}

@app.get("/api/demo/scholarships")
def demo(): return [{**s, "scholarship_status": el.status(s)} for s in SCHOLARSHIPS]

@app.post("/api/auth/register", status_code=201)
def register(b: Reg):
    c = db(); email = b.email.strip().lower(); salt = secrets.token_hex(16); code = f"{secrets.randbelow(10**6):06d}"
    try:
        c.execute("INSERT INTO students(id,email,pw,salt,vcode,profile,created_at) VALUES(?,?,?,?,?,?,?)",
                  (str(uuid.uuid4()), email, hp(b.password, salt), salt, code, json.dumps({"full_name": b.full_name, "country": "IN"}), now()))
        if email in [x.strip().lower() for x in os.environ.get("ADMIN_EMAILS", "").split(",") if x.strip()]:
            c.execute("UPDATE students SET role='admin' WHERE email=?", (email,))
        c.commit()
    except sqlite3.IntegrityError: raise err("duplicate_email", "Email already registered", 409)
    out = {"message": "Registered.", "email_delivery": mailer.send(email, "Your EduPilot verification code", f"Your verification code is {code}")}
    if DEMO: out["demo_verification_code"] = code  # only in explicit demo mode
    return out

@app.post("/api/auth/verify")
def verify(b: Verify):
    c = db(); r = c.execute("SELECT * FROM students WHERE email=?", (b.email.strip().lower(),)).fetchone()
    if not r or not hmac.compare_digest(r["vcode"] or "x", b.code): raise err("invalid_code", "Invalid verification code", 400)
    c.execute("UPDATE students SET email_verified=1,vcode=NULL WHERE id=?", (r["id"],)); c.commit(); return {"email_verified": True}

@app.post("/api/auth/login")
def login(b: Login):
    c = db(); r = c.execute("SELECT * FROM students WHERE email=?", (b.email.strip().lower(),)).fetchone()
    if not r or not hmac.compare_digest(hp(b.password, r["salt"]), r["pw"]): raise err("bad_credentials", "Incorrect email or password", 401)
    if not r["email_verified"]: raise err("not_verified", "Verify your email first", 403)
    t = secrets.token_urlsafe(32); c.execute("INSERT INTO sessions VALUES(?,?)", (th(t), r["id"])); c.commit()
    return {"token": t, "role": r["role"]}

@app.post("/api/auth/logout")
def logout(authorization: str = Header(None), u=Depends(user)):
    c = db(); c.execute("DELETE FROM sessions WHERE th=?", (th(authorization[7:]),)); c.commit(); return {"ok": True}

class Profile(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=150)
    phone_number: Optional[str] = None; date_of_birth: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    gender: Optional[Literal["Male", "Female", "Other", "Prefer_Not_To_Say"]] = None
    country: Optional[str] = None; state: Optional[str] = None; district: Optional[str] = None
    social_category: Optional[Literal["General", "SC", "ST", "OBC", "EWS", "Other"]] = None
    annual_family_income: Optional[float] = Field(None, ge=0); family_income_currency: Optional[str] = None
    education_level: Optional[Literal["School", "Intermediate", "Diploma", "Undergraduate", "Postgraduate", "Doctoral", "Professional", "Vocational", "Other"]] = None
    course_name: Optional[str] = Field(None, min_length=1, max_length=150); course_stream: Optional[str] = None
    course_year: Optional[int] = Field(None, ge=1)
    institution_name: Optional[str] = None; institution_state: Optional[str] = None
    institution_type: Optional[Literal["Government", "Private", "Government_Aided", "Deemed", "Other"]] = None
    academic_score_value: Optional[float] = Field(None, ge=0)
    academic_score_type: Optional[Literal["Percentage", "CGPA", "GPA", "Grade", "Other"]] = None
    academic_score_scale: Optional[float] = None; academic_year: Optional[str] = None
    preferred_language: Optional[Literal["English", "Hindi", "Telugu"]] = None

def prof(u): return {"student_id": u["id"], "email": u["email"], "email_verified": bool(u["email_verified"]), **json.loads(u["profile"])}

@app.get("/api/students/me")
def me(u=Depends(user)): return prof(u)

@app.put("/api/students/me")
def put_me(b: Profile, u=Depends(user)):
    p = {**json.loads(u["profile"]), **b.model_dump(exclude_unset=True)}
    c = db(); c.execute("UPDATE students SET profile=? WHERE id=?", (json.dumps(p), u["id"])); c.commit()
    return {**prof(u), **p}

@app.get("/api/students/me/completeness")
def completeness(u=Depends(user)):
    p = json.loads(u["profile"])
    ess = [f for f in ["full_name", "country", "education_level", "course_name", "preferred_language"] if not p.get(f)]
    spec = [f for f in ["state", "annual_family_income", "social_category", "gender", "academic_score_value", "academic_score_type", "institution_type"] if p.get(f) in (None, "")]
    return {"missing": {"essential": ess, "scholarship_specific": spec}, "actions": ["Complete Now", "Remind Me Later"]}

def sch(sid):
    s = next((x for x in SCHOLARSHIPS if x["scholarship_id"] == sid), None)
    if not s: raise err("not_found", "Scholarship not found", 404)
    return s

@app.get("/api/scholarships/search")
def search(q: str = "", education_level: str = "", status: str = "", u=Depends(user)):
    out = [s for s in SCHOLARSHIPS if q.lower() in (s["scholarship_name"] + s["description"] + s["provider_name"]).lower()
           and (not education_level or education_level in s["eligible_education_levels"])
           and (not status or el.status(s) == status)]
    return {"results": [{**s, "scholarship_status": el.status(s)} for s in out],
            "empty_state": None if out else "No scholarships match. Try removing a filter."}


# Local-first Document Vault and OCR endpoints (20 MB limit; authenticity is never inferred).
DOCUMENT_ROOT = Path(os.environ.get("DOCUMENT_STORAGE_DIR", str(ROOT / "data" / "documents"))).resolve()
DOCUMENT_ROOT.mkdir(parents=True, exist_ok=True)

def _document_view(row):
    return {"document_id": row["id"], "original_name": row["original_name"],
        "mime_type": row["mime_type"], "size_bytes": row["size_bytes"], "sha256": row["sha256"],
        "extraction_text": row["extraction_text"], "extraction_method": row["extraction_method"],
        "extraction_status": row["extraction_status"], "confidence": row["confidence"],
        "page_count": row["page_count"], "warnings": json.loads(row["warnings"]),
        "extracted_fields": json.loads(row["extracted_fields"]),
        "corrected_fields": json.loads(row["corrected_fields"]), "created_at": row["created_at"],
        "authenticity_verified": False}

@app.post("/api/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), u=Depends(user)):
    data = await file.read(docs.MAX_UPLOAD_BYTES + 1)
    try:
        mime, safe_name = docs.validate_upload(file.filename or "document", data)
        extraction = docs.extract_document(data, mime)
    except docs.DocumentError as exc:
        message = str(exc)
        status = 413 if "20 MB" in message else 415
        raise err("invalid_document", message, status)
    doc_id = str(uuid.uuid4()); suffix = docs.ALLOWED[mime]; stored = f"{doc_id}{suffix}"
    target = (DOCUMENT_ROOT / stored).resolve()
    if target.parent != DOCUMENT_ROOT: raise err("invalid_document_path", "Invalid storage path", 400)
    target.write_bytes(data)
    digest = docs.sha256(data)
    c = db()
    c.execute("INSERT INTO student_documents(id,student_id,original_name,stored_name,mime_type,size_bytes,sha256,extraction_text,extraction_method,extraction_status,confidence,page_count,warnings,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (doc_id, u["id"], safe_name, stored, mime, len(data), digest, extraction.text, extraction.method,
         extraction.status, extraction.confidence, extraction.page_count, json.dumps(extraction.warnings), now()))
    c.commit()
    row = c.execute("SELECT * FROM student_documents WHERE id=? AND student_id=?", (doc_id,u["id"])).fetchone()
    return _document_view(row)

@app.get("/api/documents")
def list_documents(u=Depends(user)):
    rows = db().execute("SELECT * FROM student_documents WHERE student_id=? ORDER BY created_at DESC", (u["id"],)).fetchall()
    return [_document_view(r) for r in rows]

@app.get("/api/documents/{document_id}")
def get_document(document_id: str, u=Depends(user)):
    row = db().execute("SELECT * FROM student_documents WHERE id=? AND student_id=?", (document_id,u["id"])).fetchone()
    if not row: raise err("document_not_found", "Document not found", 404)
    return _document_view(row)

class DocumentCorrection(BaseModel):
    corrected_fields: dict[str, str] = Field(default_factory=dict)

@app.patch("/api/documents/{document_id}/corrections")
def correct_document(document_id: str, body: DocumentCorrection, u=Depends(user)):
    if len(body.corrected_fields) > 100 or any(len(k)>80 or len(v)>1000 for k,v in body.corrected_fields.items()):
        raise err("invalid_corrections", "Too many or oversized correction fields", 422)
    c=db(); row=c.execute("SELECT id FROM student_documents WHERE id=? AND student_id=?",(document_id,u["id"])).fetchone()
    if not row: raise err("document_not_found", "Document not found", 404)
    c.execute("UPDATE student_documents SET corrected_fields=? WHERE id=? AND student_id=?",
              (json.dumps(body.corrected_fields),document_id,u["id"])); c.commit()
    return get_document(document_id,u)

@app.get("/api/documents/consistency/conflicts")
def document_conflicts(u=Depends(user)):
    rows=db().execute("SELECT id,extracted_fields,corrected_fields FROM student_documents WHERE student_id=?",(u["id"],)).fetchall()
    items=[{"document_id":r["id"],"extracted_fields":json.loads(r["extracted_fields"]),"corrected_fields":json.loads(r["corrected_fields"])} for r in rows]
    return {"conflicts":docs.compare_extracted_fields(items),"note":"Conflicts require student review; the system does not decide which document is correct."}

@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str, u=Depends(user)):
    c=db(); row=c.execute("SELECT stored_name FROM student_documents WHERE id=? AND student_id=?",(document_id,u["id"])).fetchone()
    if not row: raise err("document_not_found", "Document not found", 404)
    path=(DOCUMENT_ROOT / row["stored_name"]).resolve()
    if path.parent == DOCUMENT_ROOT and path.exists(): path.unlink()
    c.execute("DELETE FROM student_documents WHERE id=? AND student_id=?",(document_id,u["id"])); c.commit()
    return {"deleted": True, "document_id": document_id}

@app.get("/api/scholarships")
def list_s(u=Depends(user)): return [{**s, "scholarship_status": el.status(s)} for s in SCHOLARSHIPS]

@app.get("/api/scholarships/{sid}")
def get_s(sid: str, u=Depends(user)): return {**sch(sid), "scholarship_status": el.status(sch(sid))}

class Assess(BaseModel): scholarship_ids: list[str]

@app.post("/api/eligibility/assess")
def assess(b: Assess, u=Depends(user)):
    p = json.loads(u["profile"])
    return [{"assessment_id": str(uuid.uuid4()), "student_id": u["id"], **el.assess(sch(i), p), "assessed_at": now()} for i in b.scholarship_ids]

@app.get("/api/recommendations")
def recs(u=Depends(user)):
    p, out = json.loads(u["profile"]), []
    for s in SCHOLARSHIPS:
        a = el.assess(s, p)
        if a["eligibility_status"] == "not_eligible": continue
        r = el.rank_score(s, p)
        out.append({"scholarship_id": s["scholarship_id"], "scholarship_name": s["scholarship_name"], "eligibility_status": a["eligibility_status"],
                    "closing_date": s["closing_date"], "verification_status": s["verification_status"], "is_demo": s.get("is_demo", False), **r})
    order = {"likely_eligible": 0, "possibly_eligible": 1, "more_information_required": 2}
    out.sort(key=lambda x: (-(x["relevance_score"] if x["relevance_score"] is not None else -1), order[x["eligibility_status"]], x["closing_date"] or "9", x["scholarship_name"]))
    for i, x in enumerate(out, 1): x["ranking_position"] = i
    return out

class Prep(BaseModel): scholarship_id: str
class Upd(BaseModel): answers: Optional[dict] = None; documents_confirmed: Optional[list[str]] = None
class Appr(BaseModel): decision: Literal["approve", "decline"]

def app_row(aid, u):
    c = db(); r = c.execute("SELECT * FROM applications WHERE id=? AND student_id=?", (aid, u["id"])).fetchone()
    if not r: raise err("not_found", "Application not found", 404)
    return c, r
def view(r):
    return {"application_id": r["id"], "scholarship_id": r["scholarship_id"], "application_status": r["status"], "approved": bool(r["approved"]), **json.loads(r["data"]), "timeline": json.loads(r["timeline"])}
def save(c, r, status, d, approved=None, ev=None):
    tl = json.loads(r["timeline"]) + ([{"event": ev, "event_source": "Student_Update", "verification_status": "Unverified", "recorded_at": now()}] if ev else [])
    c.execute("UPDATE applications SET status=?,data=?,approved=?,timeline=? WHERE id=?", (status, json.dumps(d), r["approved"] if approved is None else approved, json.dumps(tl), r["id"])); c.commit()
def missing_docs(s, d): return [x for x in s["required_documents"] if x not in d["documents_confirmed"]]

@app.post("/api/applications/prepare", status_code=201)
def prepare(b: Prep, u=Depends(user)):
    s, p = sch(b.scholarship_id), json.loads(u["profile"])
    if el.status(s) != "Open": raise err("not_open", f"Scholarship is {el.status(s)}", 409)
    fields = {k: {"value": p.get(k), "source": "profile"} for k in ["full_name", "course_name", "education_level", "institution_name", "state"] if p.get(k)}
    d = {"form_fields": fields, "answers": {}, "documents_confirmed": [], "missing_documents": s["required_documents"]}
    aid = str(uuid.uuid4()); c = db()
    c.execute("INSERT INTO applications(id,student_id,scholarship_id,status,data,timeline) VALUES(?,?,?,?,?,?)",
              (aid, u["id"], s["scholarship_id"], "Draft", json.dumps(d), json.dumps([{"event": "Draft created", "event_source": "Student_Update", "verification_status": "Unverified", "recorded_at": now()}]))); c.commit()
    return view(c.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone())

@app.get("/api/applications")
def list_apps(u=Depends(user)): return [view(r) for r in db().execute("SELECT * FROM applications WHERE student_id=?", (u["id"],))]

@app.get("/api/applications/{aid}/readiness")
def ready(aid: str, u=Depends(user)):
    c, r = app_row(aid, u); m = missing_docs(sch(r["scholarship_id"]), json.loads(r["data"]))
    return {"ready": not m, "missing_documents": m, "note": "Automated checks do not verify document authenticity."}

@app.put("/api/applications/{aid}")
def upd(aid: str, b: Upd, u=Depends(user)):
    c, r = app_row(aid, u)
    if r["status"] in ("Submitted", "Approved", "Rejected"): raise err("invalid_state", "Application can no longer be edited", 409)
    d = json.loads(r["data"])
    if b.answers is not None: d["answers"] = b.answers
    if b.documents_confirmed is not None: d["documents_confirmed"] = b.documents_confirmed
    d["missing_documents"] = missing_docs(sch(r["scholarship_id"]), d)
    save(c, r, "Ready_For_Review" if not d["missing_documents"] else "Draft", d, approved=0, ev="Draft edited; approval reset")
    return view(c.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone())

@app.post("/api/applications/{aid}/approval")
def approval(aid: str, b: Appr, u=Depends(user)):
    c, r = app_row(aid, u)
    if r["status"] not in ("Ready_For_Review", "Awaiting_Approval"): raise err("invalid_state", "Application must be Ready_For_Review first", 409, {"status": r["status"]})
    ok = b.decision == "approve"
    save(c, r, "Awaiting_Approval" if ok else "Ready_For_Review", json.loads(r["data"]), approved=int(ok), ev=f"Student decision: {b.decision}")
    return view(c.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone())

@app.post("/api/applications/{aid}/submit", status_code=202)
def submit(aid: str, u=Depends(user)):
    c, r = app_row(aid, u)
    if r["status"] != "Awaiting_Approval" or not r["approved"]: raise err("approval_required", "Explicit student approval is required before submission", 409)
    # No portal integration exists, so nothing is submitted and Submitted is NOT recorded (needs provider confirmation).
    return {"application_status": r["status"], "submitted": False, "mode": "guided_manual",
            "message": "No supported portal integration is configured. Complete submission on the official portal, then add your acknowledgement as a student update."}

@app.get("/api/applications/{aid}/status")
def st(aid: str, u=Depends(user)):
    c, r = app_row(aid, u); tl = json.loads(r["timeline"])
    return {"application_status": r["status"], "last_event": tl[-1] if tl else None, "verification_status": "Unverified"}

@app.get("/api/applications/{aid}/timeline")
def tl(aid: str, u=Depends(user)): return json.loads(app_row(aid, u)[1]["timeline"])

from backend import extras
extras.setup(app, user, db, err, now, sch, SCHOLARSHIPS, el)
from backend import more
more.setup(app, user, db, err, now, SCHOLARSHIPS, sch, el)
from backend import ingest
ingest.setup(app, user, db, err, now, SCHOLARSHIPS, el)
from backend import export_search
export_search.setup(app, user, db, now, sch, SCHOLARSHIPS, el)
from backend import automation
automation.setup(app, user, db, err, now, sch, el)
from backend import aicost, crawl, scheduler
from backend.ai import assistant_api
aicost.setup(app, user, db, err, now)
crawl.setup(app, user, db, err, now, SCHOLARSHIPS)
assistant_api.setup(app, user, db, err, now, SCHOLARSHIPS, el)
@app.on_event("startup")
def _start_scheduler(): scheduler.start()
# Stage 5: explicit administrator review of scholarship source provenance.
from backend import source_registry
source_registry.setup(app, user, db, err, now)

# Stage 6: provider-neutral application preparation and validation workspace.
from backend import application_workflow
application_workflow.setup(app, user, db, err, now, sch)

# Mount the frontend after API registration so API routes are not shadowed.

# Stage 7: application status history, separate payment records and renewals.
from backend import tracking
tracking.setup(app, user, db, err, now)

# Stage 11: safe guided handoff to configured official scholarship portals.
from backend import portal_handoff
portal_handoff.setup(app, user, db, err, now, sch)

# Stage 8: personalised scholarship alerts and scheduled deadline/renewal reminders.
from backend import alerts
alerts.setup(app, user, db, err, now, SCHOLARSHIPS, el)

# Stage 12: baseline security headers, optional API rate limiting and readiness checks.
from backend import hardening
hardening.setup(app, DB_PATH)

# Mount frontend last so later API routes remain reachable.
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
