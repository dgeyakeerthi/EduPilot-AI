"""Admin-controlled source registry. Automated discovery never marks a source official."""
import hashlib, ipaddress, json, socket, uuid
from urllib.parse import urlparse
from fastapi import Depends
from pydantic import BaseModel, Field

class SourceCandidate(BaseModel):
    provider_name: str = Field(min_length=2, max_length=200)
    url: str = Field(pattern=r"^https://\S+$", max_length=500)
    source_type: str = Field(default="ScholarshipProvider", max_length=60)
    evidence_url: str | None = Field(default=None, max_length=500)

class SourceReview(BaseModel):
    decision: str = Field(pattern=r"^(verify|reject)$")
    verification_notes: str = Field(min_length=10, max_length=2000)
    evidence_url: str | None = Field(default=None, max_length=500)

def _public_https(url):
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise ValueError("A public HTTPS URL is required")
    try:
        addresses = socket.getaddrinfo(p.hostname, p.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Source hostname could not be resolved") from exc
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError("Private or non-public source addresses are not allowed")
    return p

def setup(app, user, db, err, now):
    def conn():
        c = db()
        c.executescript("""
          CREATE TABLE IF NOT EXISTS scholarship_sources(
            id TEXT PRIMARY KEY, provider_name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
            host TEXT NOT NULL, source_type TEXT NOT NULL, evidence_url TEXT,
            status TEXT NOT NULL DEFAULT 'Pending_Verification', submitted_by TEXT NOT NULL,
            reviewed_by TEXT, reviewed_at TEXT, verification_notes TEXT,
            created_at TEXT NOT NULL, content_sha256 TEXT
          );
          CREATE TABLE IF NOT EXISTS source_registry_audit(
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL, actor_id TEXT NOT NULL,
            action TEXT NOT NULL, notes TEXT NOT NULL, created_at TEXT NOT NULL
          );
        """)
        return c
    def admin(u):
        if u["role"] != "admin": raise err("forbidden", "Administrator access required", 403)

    @app.post("/api/admin/source-registry", status_code=201)
    def submit_source(body: SourceCandidate, u=Depends(user)):
        admin(u)
        try: parsed = _public_https(body.url)
        except Exception as exc: raise err("invalid_source", str(exc), 422)
        if body.evidence_url:
            try: _public_https(body.evidence_url)
            except Exception as exc: raise err("invalid_evidence_url", str(exc), 422)
        sid = str(uuid.uuid4()); c = conn()
        try:
            c.execute("INSERT INTO scholarship_sources(id,provider_name,url,host,source_type,evidence_url,submitted_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (sid, body.provider_name.strip(), body.url, parsed.hostname.lower(), body.source_type,
                       body.evidence_url, u["id"], now()))
            c.commit()
        except Exception:
            raise err("duplicate_source", "This source URL is already registered", 409)
        return {"source_id": sid, "status": "Pending_Verification", "message": "Source submitted for human verification; it is not yet trusted."}

    @app.get("/api/admin/source-registry")
    def list_sources(status: str = "", u=Depends(user)):
        admin(u); c=conn()
        rows = c.execute("SELECT * FROM scholarship_sources WHERE (?='' OR status=?) ORDER BY created_at DESC", (status,status)).fetchall()
        return [{k:r[k] for k in ("id","provider_name","url","host","source_type","evidence_url","status","reviewed_at","verification_notes","created_at")} for r in rows]

    @app.post("/api/admin/source-registry/{source_id}/review")
    def review_source(source_id: str, body: SourceReview, u=Depends(user)):
        admin(u); c=conn()
        row=c.execute("SELECT * FROM scholarship_sources WHERE id=?", (source_id,)).fetchone()
        if not row: raise err("not_found", "Source not found", 404)
        if row["status"] != "Pending_Verification": raise err("invalid_state", "Only pending sources can be reviewed", 409)
        evidence = body.evidence_url or row["evidence_url"]
        if body.decision == "verify" and not evidence:
            raise err("evidence_required", "Provide an official evidence URL before verification", 422)
        if evidence:
            try: _public_https(evidence)
            except Exception as exc: raise err("invalid_evidence_url", str(exc), 422)
        status = "Verified_Official" if body.decision == "verify" else "Rejected"
        c.execute("UPDATE scholarship_sources SET status=?,evidence_url=?,reviewed_by=?,reviewed_at=?,verification_notes=? WHERE id=?",
                  (status,evidence,u["id"],now(),body.verification_notes,source_id))
        c.execute("INSERT INTO source_registry_audit VALUES(?,?,?,?,?,?)",
                  (str(uuid.uuid4()),source_id,u["id"],status,body.verification_notes,now()))
        c.commit()
        return {"source_id":source_id,"status":status,"note":"Verification is an administrator decision, not an automated authenticity guarantee."}

    @app.get("/api/admin/source-registry/{source_id}/history")
    def source_history(source_id: str, u=Depends(user)):
        admin(u); c=conn()
        if not c.execute("SELECT 1 FROM scholarship_sources WHERE id=?",(source_id,)).fetchone(): raise err("not_found","Source not found",404)
        return [dict(r) for r in c.execute("SELECT action,notes,created_at FROM source_registry_audit WHERE source_id=? ORDER BY created_at",(source_id,))]
