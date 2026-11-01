"""Stage 11: safe, student-controlled handoff to official scholarship portals.

This module deliberately does not automate login, OTP, CAPTCHA, declarations,
payments, signatures, biometrics or final submission. It prepares a reviewable
copy of allowed application fields and records student-confirmed checkpoints.
"""
from __future__ import annotations
import json, uuid
from urllib.parse import urlparse
from pydantic import BaseModel, Field
from fastapi import Depends

BLOCKED = {"otp", "captcha", "password", "bank_account", "ifsc", "payment", "signature", "biometric", "declaration"}
CHECKPOINTS = [
    "Open the official scholarship portal",
    "Sign in or create your account yourself",
    "Review and enter the prepared application details",
    "Upload the required documents yourself",
    "Complete OTP, CAPTCHA and identity checks yourself if requested",
    "Review declarations and payment-related steps yourself",
    "Submit on the official portal yourself and save its acknowledgement",
]

class CheckpointUpdate(BaseModel):
    checkpoint_index: int = Field(ge=0, le=6)
    completed: bool
    note: str | None = Field(default=None, max_length=300)


def safe_https(url: str | None) -> bool:
    try:
        p = urlparse(url or "")
        return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password
    except Exception:
        return False


def setup(app, user_dep, db, err, now, sch):
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS portal_handoff_sessions(
      id TEXT PRIMARY KEY, application_id TEXT NOT NULL, student_id TEXT NOT NULL,
      portal_url TEXT NOT NULL, checkpoints TEXT NOT NULL, created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL)""")
    c.commit()

    def owned(aid, u):
        row = db().execute("SELECT * FROM applications WHERE id=? AND student_id=?", (aid, u["id"])).fetchone()
        if not row: raise err("not_found", "Application not found", 404)
        return row

    def safe_fields(data):
        out = {}
        for key, entry in data.get("form_fields", {}).items():
            if any(term in key.lower() for term in BLOCKED):
                continue
            value = entry.get("value") if isinstance(entry, dict) else entry
            if value is not None:
                out[key] = {"value": value, "source": entry.get("source", "application_draft") if isinstance(entry, dict) else "application_draft"}
        return out

    @app.get("/api/applications/{aid}/portal-handoff")
    def handoff_preview(aid: str, u=Depends(user_dep)):
        row = owned(aid, u); scholarship = sch(row["scholarship_id"])
        target = scholarship.get("application_url")
        return {"application_id": aid, "portal_available": safe_https(target),
                "portal_url": target if safe_https(target) else None,
                "prepared_fields": safe_fields(json.loads(row["data"] or "{}")),
                "required_documents": scholarship.get("required_documents", []),
                "manual_checkpoints": CHECKPOINTS,
                "automated_actions": [],
                "safety_note": "This is a guided handoff only. EduPilot does not log in, bypass security checks, make declarations, pay fees or submit the application."}

    @app.post("/api/applications/{aid}/portal-handoff", status_code=201)
    def create_handoff(aid: str, u=Depends(user_dep)):
        row = owned(aid, u); scholarship = sch(row["scholarship_id"]); target = scholarship.get("application_url")
        if not safe_https(target):
            raise err("portal_not_configured", "No verified HTTPS application portal URL is configured for this scholarship", 409)
        sid = str(uuid.uuid4()); stamp = now()
        state = [{"label": label, "completed": False, "student_confirmed_at": None, "note": None} for label in CHECKPOINTS]
        c = db(); c.execute("INSERT INTO portal_handoff_sessions(id,application_id,student_id,portal_url,checkpoints,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (sid, aid, u["id"], target, json.dumps(state), stamp, stamp)); c.commit()
        return {"session_id": sid, "application_id": aid, "portal_url": target, "checkpoints": state,
                "message": "Guided handoff created. Open the official portal and complete each restricted step yourself."}

    @app.get("/api/portal-handoff/{sid}")
    def get_handoff(sid: str, u=Depends(user_dep)):
        row = db().execute("SELECT * FROM portal_handoff_sessions WHERE id=? AND student_id=?", (sid, u["id"])).fetchone()
        if not row: raise err("not_found", "Portal handoff session not found", 404)
        return {"session_id": sid, "application_id": row["application_id"], "portal_url": row["portal_url"],
                "checkpoints": json.loads(row["checkpoints"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}

    @app.patch("/api/portal-handoff/{sid}/checkpoint")
    def update_checkpoint(sid: str, body: CheckpointUpdate, u=Depends(user_dep)):
        c = db(); row = c.execute("SELECT * FROM portal_handoff_sessions WHERE id=? AND student_id=?", (sid, u["id"])).fetchone()
        if not row: raise err("not_found", "Portal handoff session not found", 404)
        checkpoints = json.loads(row["checkpoints"]); item = checkpoints[body.checkpoint_index]
        item["completed"] = body.completed; item["student_confirmed_at"] = now() if body.completed else None
        # Never accept sensitive values, credentials, OTPs or payment details in notes.
        note = body.note
        if note and any(term in note.lower() for term in BLOCKED):
            raise err("restricted_content", "Do not enter credentials, OTPs, bank details, declarations or payment information here", 422)
        item["note"] = note
        stamp = now(); c.execute("UPDATE portal_handoff_sessions SET checkpoints=?,updated_at=? WHERE id=? AND student_id=?",
            (json.dumps(checkpoints), stamp, sid, u["id"])); c.commit()
        return {"session_id": sid, "checkpoints": checkpoints, "provider_submission_confirmed": False,
                "message": "Checkpoint recorded as student-reported progress only."}
