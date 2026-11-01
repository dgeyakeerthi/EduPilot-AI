"""Persistent local Nomic semantic search with explicit lexical fallback."""
import json, math, os, re
from functools import lru_cache
from fastapi import Depends, Response
from backend.pdf import make_pdf
from backend.embeddings import LocalNomicIndex, EmbeddingUnavailable, DEFAULT_MODEL

_INDEX = None
_INDEX_MODEL = None

def _lexical_rank(q, docs, k):
    terms = set(re.findall(r"[a-z0-9]+", q.lower()))
    scores=[]
    for i, doc in enumerate(docs):
        words=set(re.findall(r"[a-z0-9]+", doc.lower()))
        score=len(terms & words)/max(1, len(terms | words))
        if score: scores.append((i, score))
    return sorted(scores, key=lambda x: -x[1])[:k]

def rank(q, docs, k=5):
    global _INDEX, _INDEX_MODEL
    if not docs: return [], "none"
    model = os.environ.get("EMBED_MODEL", DEFAULT_MODEL)
    try:
        if _INDEX is None or _INDEX_MODEL != model:
            _INDEX = LocalNomicIndex(model=model)
            _INDEX_MODEL = model
        _INDEX.ensure(docs)
        found = _INDEX.search(q, k)
        return [(i, score) for i, score in found if score > 0], f"ollama:{model}+{_INDEX.backend}+persistent"
    except Exception as exc:
        return _lexical_rank(q, docs, k), "lexical-fallback (local embeddings unavailable: " + type(exc).__name__ + ")"

def setup(app, user, db, now, sch, SCH, el):
    @app.get("/api/search/semantic")
    def semantic(q: str, u=Depends(user)):
        docs=[f'{s["scholarship_name"]} {s["provider_name"]} {s["description"]} {" ".join(s["eligible_education_levels"])}' for s in SCH]
        res, method=rank(q[:300],docs)
        return {"method":method,"embedding_model":os.environ.get("EMBED_MODEL",DEFAULT_MODEL),"results":[{"scholarship_id":SCH[j]["scholarship_id"],"scholarship_name":SCH[j]["scholarship_name"],"score":round(score,3),"scholarship_status":el.status(SCH[j])} for j,score in res],"empty_state":None if res else "No close matches. Try different words."}

    @app.get("/api/ai/status")
    def ai_status(u=Depends(user)):
        return {"primary_model":os.environ.get("GEMINI_PRIMARY_MODEL","gemini-3.8-flash"),"local_llm":os.environ.get("LOCAL_LLM_MODEL","qwen3:4b"),"embedding_model":os.environ.get("EMBED_MODEL",DEFAULT_MODEL),"embedding_provider":"Ollama local","faiss_optional":True,"index_persistence":"enabled","note":"Embedding readiness is confirmed only by a successful semantic-search request."}

    @app.get("/api/exports/applications.pdf")
    def pdf(u=Depends(user)):
        rows=db().execute("SELECT * FROM applications WHERE student_id=?",(u["id"],)).fetchall()
        lines=[f"Generated {now()[:10]}. Student-reported statuses are unverified.",""]
        for r in rows:
            d=json.loads(r["data"]); lines.append(f'{sch(r["scholarship_id"])["scholarship_name"]} | {r["status"]} | approved: {bool(r["approved"])} | payment: {d.get("payment_status","n/a")}')
        if not rows: lines.append("No applications yet.")
        return Response(make_pdf("EduPilot AI - My applications",lines),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=applications.pdf"})
