"""Stage 6 application preparation, validation and student-controlled workflow."""
from __future__ import annotations
import json, uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import Depends
from pydantic import BaseModel, Field

# Field definitions are conservative defaults. Providers may later supply portal-specific
# schemas; never infer legal declarations or submit them automatically.
PROFILE_FIELDS = {
    "full_name": {"label": "Full name", "type": "text", "required": True},
    "date_of_birth": {"label": "Date of birth", "type": "date", "required": False},
    "phone_number": {"label": "Phone number", "type": "tel", "required": False},
    "education_level": {"label": "Education level", "type": "text", "required": True},
    "course_name": {"label": "Course name", "type": "text", "required": False},
    "course_year": {"label": "Current year of study", "type": "number", "required": False},
    "institution_name": {"label": "Institution name", "type": "text", "required": True},
    "institution_type": {"label": "Institution type", "type": "text", "required": False},
    "state": {"label": "State", "type": "text", "required": True},
    "district": {"label": "District", "type": "text", "required": False},
    "annual_family_income": {"label": "Annual family income (INR)", "type": "number", "required": False},
    "social_category": {"label": "Social category", "type": "text", "required": False},
    "academic_score_value": {"label": "Academic score", "type": "number", "required": False},
    "academic_score_type": {"label": "Score type", "type": "text", "required": False},
}
RESTRICTED_KEYS = {"bank_account", "ifsc", "otp", "captcha", "biometric", "signature", "declaration", "payment"}

class FieldUpdate(BaseModel):
    form_fields: dict[str, Any] = Field(default_factory=dict)
    answers: dict[str, Any] = Field(default_factory=dict)
    documents_confirmed: list[str] | None = None

def setup(app, user_dep, db, err, now, sch):
    def get_row(aid, u):
        row = db().execute("SELECT * FROM applications WHERE id=? AND student_id=?", (aid, u["id"])).fetchone()
        if not row: raise err("not_found", "Application not found", 404)
        return row

    def parse(row): return json.loads(row["data"] or "{}")
    def persist(c, row, data, status, event):
        timeline = json.loads(row["timeline"] or "[]")
        timeline.append({"event": event, "event_source": "Student_Update", "verification_status": "Unverified", "recorded_at": now()})
        c.execute("UPDATE applications SET data=?,status=?,approved=0,timeline=? WHERE id=? AND student_id=?",
                  (json.dumps(data), status, json.dumps(timeline), row["id"], row["student_id"]))
        c.commit()
        return c.execute("SELECT * FROM applications WHERE id=? AND student_id=?", (row["id"], row["student_id"])).fetchone()

    @app.get("/api/applications/{aid}/form-schema")
    def application_form_schema(aid: str, u=Depends(user_dep)):
        row = get_row(aid, u); data = parse(row); scholarship = sch(row["scholarship_id"])
        fields = []
        for key, spec in PROFILE_FIELDS.items():
            current = data.get("form_fields", {}).get(key, {})
            fields.append({"key": key, **spec, "value": current.get("value"), "source": current.get("source", "not_provided"), "editable": True})
        return {"application_id": aid, "scholarship_id": scholarship["scholarship_id"], "scholarship_name": scholarship["scholarship_name"],
                "fields": fields, "required_documents": scholarship.get("required_documents", []),
                "restricted_steps": ["OTP", "CAPTCHA", "biometric verification", "payments", "mandatory declarations", "bank details"],
                "note": "This is a preparation schema, not the provider's official form. Confirm all fields on the official portal."}

    @app.patch("/api/applications/{aid}/workspace")
    def update_workspace(aid: str, body: FieldUpdate, u=Depends(user_dep)):
        c = db(); row = get_row(aid, u)
        if row["status"] in ("Submitted", "Provider_Approved", "Rejected", "Withdrawn"):
            raise err("invalid_state", "This application can no longer be edited", 409)
        data = parse(row); fields = data.setdefault("form_fields", {})
        for key, value in body.form_fields.items():
            if key not in PROFILE_FIELDS: raise err("unknown_application_field", f"Unsupported field: {key}", 422)
            if any(token in key.lower() for token in RESTRICTED_KEYS): raise err("restricted_field", "Restricted fields cannot be automated", 422)
            if isinstance(value, str) and len(value) > 500: raise err("field_too_long", f"{key} exceeds 500 characters", 422)
            fields[key] = {"value": value, "source": "student_confirmed", "updated_at": now()}
        data["answers"].update(body.answers)
        if body.documents_confirmed is not None:
            available = {x["id"] for x in c.execute("SELECT id FROM student_documents WHERE student_id=?", (u["id"],)).fetchall()}
            unknown = sorted(set(body.documents_confirmed) - available)
            if unknown: raise err("document_access_denied", "Only documents in your own vault can be linked", 403, {"document_ids": unknown})
            data["documents_confirmed"] = body.documents_confirmed
        scholarship = sch(row["scholarship_id"])
        data["missing_documents"] = [x for x in scholarship.get("required_documents", []) if x not in data.get("documents_confirmed", [])]
        required_missing = [k for k, spec in PROFILE_FIELDS.items() if spec["required"] and not fields.get(k, {}).get("value")]
        data["missing_required_fields"] = required_missing
        status = "Ready_For_Review" if not data["missing_documents"] and not required_missing else "Draft"
        updated = persist(c, row, data, status, "Student updated application workspace")
        return {"application_id": aid, "application_status": status, "missing_documents": data["missing_documents"], "missing_required_fields": required_missing,
                "form_fields": data["form_fields"], "approval_reset": True}

    @app.post("/api/applications/{aid}/validate")
    def validate_workspace(aid: str, u=Depends(user_dep)):
        row = get_row(aid, u); data = parse(row); scholarship = sch(row["scholarship_id"])
        fields = data.get("form_fields", {})
        missing_fields = [k for k, spec in PROFILE_FIELDS.items() if spec["required"] and not fields.get(k, {}).get("value")]
        missing_docs = [x for x in scholarship.get("required_documents", []) if x not in data.get("documents_confirmed", [])]
        warnings = []
        if scholarship.get("is_demo"): warnings.append("This is a fictional demonstration scholarship, not a real opportunity.")
        if scholarship.get("verification_status") != "Human_Verified": warnings.append("Scholarship information has not completed human verification.")
        warnings.append("Document presence does not establish authenticity or correctness.")
        warnings.append("Provider-specific fields and official portal requirements must be checked manually.")
        return {"valid_for_student_review": not missing_fields and not missing_docs, "missing_required_fields": missing_fields,
                "missing_documents": missing_docs, "warnings": warnings, "submission_allowed": False,
                "reason": "This workflow prepares and validates a draft. It does not submit applications to providers."}

    @app.get("/api/applications/{aid}/workspace")
    def get_workspace(aid: str, u=Depends(user_dep)):
        row = get_row(aid, u); data = parse(row)
        return {"application_id": aid, "application_status": row["status"], "approved": bool(row["approved"]),
                "form_fields": data.get("form_fields", {}), "answers": data.get("answers", {}),
                "documents_confirmed": data.get("documents_confirmed", []), "missing_documents": data.get("missing_documents", [])}
