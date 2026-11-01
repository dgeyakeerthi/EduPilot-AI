"""Stage 7: student-assisted application tracking, separate payment records and renewals.

Provider status is never inferred. Student-entered updates remain Unverified until an
administrator records a review; this module does not claim a live provider integration.
"""
from __future__ import annotations
import json, uuid
from datetime import date, datetime, timezone
from typing import Optional, Literal
from fastapi import Depends
from pydantic import BaseModel, Field

APP_STATUSES = {"Draft", "Ready_For_Review", "Awaiting_Approval", "Submitted", "Under_Review", "Correction_Required", "Provider_Approved", "Rejected", "Withdrawn", "Unknown"}
PAYMENT_STATUSES = {"Not_Reported", "Pending", "Processing", "Paid", "Failed", "On_Hold", "Unknown"}
RENEWAL_STATUSES = {"Upcoming", "In_Progress", "Submitted", "Renewed", "Not_Continuing", "Expired"}

class ApplicationUpdate(BaseModel):
    status: Literal["Submitted", "Under_Review", "Correction_Required", "Provider_Approved", "Rejected", "Withdrawn", "Unknown"]
    note: str = Field(default="", max_length=1000)
    acknowledgement_reference: Optional[str] = Field(default=None, max_length=200)
    evidence_document_id: Optional[str] = None

class PaymentCreate(BaseModel):
    application_id: str
    amount: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    reported_status: Literal["Pending", "Processing", "Paid", "Failed", "On_Hold", "Unknown"]
    transaction_reference: Optional[str] = Field(default=None, max_length=200)
    reported_at: Optional[str] = None
    note: str = Field(default="", max_length=1000)

class PaymentReview(BaseModel):
    status: Literal["Pending", "Processing", "Paid", "Failed", "On_Hold", "Unknown"]
    review_note: str = Field(min_length=1, max_length=1000)

class RenewalCreate(BaseModel):
    application_id: str
    academic_year: str = Field(min_length=4, max_length=20)
    deadline: Optional[str] = None
    status: Literal["Upcoming", "In_Progress", "Submitted", "Renewed", "Not_Continuing", "Expired"] = "Upcoming"
    notes: str = Field(default="", max_length=1000)

class RenewalUpdate(BaseModel):
    deadline: Optional[str] = None
    status: Optional[Literal["Upcoming", "In_Progress", "Submitted", "Renewed", "Not_Continuing", "Expired"]] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


def setup(app, user_dep, db, err, now):
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS application_status_events(
      id TEXT PRIMARY KEY, application_id TEXT NOT NULL, student_id TEXT NOT NULL,
      status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', acknowledgement_reference TEXT,
      evidence_document_id TEXT, verification_status TEXT NOT NULL DEFAULT 'Unverified',
      source TEXT NOT NULL DEFAULT 'Student_Reported', created_at TEXT NOT NULL,
      reviewed_by TEXT, reviewed_at TEXT, review_note TEXT);
    CREATE TABLE IF NOT EXISTS scholarship_payments(
      id TEXT PRIMARY KEY, application_id TEXT NOT NULL, student_id TEXT NOT NULL,
      amount REAL, currency TEXT NOT NULL, reported_status TEXT NOT NULL,
      verified_status TEXT NOT NULL DEFAULT 'Unverified', transaction_reference TEXT,
      reported_at TEXT, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
      reviewed_by TEXT, reviewed_at TEXT, review_note TEXT);
    CREATE TABLE IF NOT EXISTS scholarship_renewals(
      id TEXT PRIMARY KEY, application_id TEXT NOT NULL, student_id TEXT NOT NULL,
      academic_year TEXT NOT NULL, deadline TEXT, status TEXT NOT NULL,
      notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(application_id, academic_year));
    CREATE INDEX IF NOT EXISTS idx_app_events_owner ON application_status_events(student_id, application_id);
    CREATE INDEX IF NOT EXISTS idx_payments_owner ON scholarship_payments(student_id, application_id);
    CREATE INDEX IF NOT EXISTS idx_renewals_owner ON scholarship_renewals(student_id, deadline);
    """)
    c.commit()

    def owned_application(c, aid, u):
        row = c.execute("SELECT * FROM applications WHERE id=? AND student_id=?", (aid, u["id"])).fetchone()
        if not row: raise err("not_found", "Application not found", 404)
        return row

    def admin(u):
        if u["role"] != "admin": raise err("forbidden", "Administrator access required", 403)

    @app.post("/api/applications/{aid}/tracking-updates", status_code=201)
    def add_application_update(aid: str, body: ApplicationUpdate, u=Depends(user_dep)):
        c=db(); owned_application(c, aid, u)
        if body.evidence_document_id:
            doc=c.execute("SELECT id FROM student_documents WHERE id=? AND student_id=?", (body.evidence_document_id,u["id"])).fetchone()
            if not doc: raise err("document_access_denied", "Evidence document must belong to your vault", 403)
        eid=str(uuid.uuid4())
        c.execute("INSERT INTO application_status_events(id,application_id,student_id,status,note,acknowledgement_reference,evidence_document_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (eid,aid,u["id"],body.status,body.note,body.acknowledgement_reference,body.evidence_document_id,now()))
        # Do not overwrite the application state with an unverified student report.
        c.commit()
        return {"event_id":eid,"application_id":aid,"reported_status":body.status,"verification_status":"Unverified","message":"Student-reported status; not confirmed by the scholarship provider."}

    @app.get("/api/applications/{aid}/tracking-updates")
    def application_updates(aid: str, u=Depends(user_dep)):
        c=db(); owned_application(c,aid,u)
        rows=c.execute("SELECT * FROM application_status_events WHERE application_id=? AND student_id=? ORDER BY created_at DESC",(aid,u["id"])).fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/payments", status_code=201)
    def report_payment(body: PaymentCreate, u=Depends(user_dep)):
        c=db(); owned_application(c,body.application_id,u)
        if body.reported_at:
            try: datetime.fromisoformat(body.reported_at.replace("Z","+00:00"))
            except ValueError: raise err("invalid_date", "reported_at must be an ISO-8601 timestamp", 422)
        pid=str(uuid.uuid4())
        c.execute("INSERT INTO scholarship_payments(id,application_id,student_id,amount,currency,reported_status,transaction_reference,reported_at,note,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (pid,body.application_id,u["id"],body.amount,body.currency.upper(),body.reported_status,body.transaction_reference,body.reported_at,body.note,now()))
        c.commit()
        return {"payment_id":pid,"application_id":body.application_id,"reported_status":body.reported_status,"verified_status":"Unverified","message":"Payment status is recorded separately from application status and is not provider-verified."}

    @app.get("/api/payments")
    def list_payments(u=Depends(user_dep)):
        return [dict(r) for r in db().execute("SELECT * FROM scholarship_payments WHERE student_id=? ORDER BY created_at DESC",(u["id"],)).fetchall()]

    @app.post("/api/admin/payments/{payment_id}/review")
    def review_payment(payment_id: str, body: PaymentReview, u=Depends(user_dep)):
        admin(u); c=db(); row=c.execute("SELECT id FROM scholarship_payments WHERE id=?",(payment_id,)).fetchone()
        if not row: raise err("not_found", "Payment record not found", 404)
        c.execute("UPDATE scholarship_payments SET verified_status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?",
                  (body.status,u["id"],now(),body.review_note,payment_id)); c.commit()
        return {"payment_id":payment_id,"verified_status":body.status,"reviewed":True}

    @app.post("/api/renewals", status_code=201)
    def create_renewal(body: RenewalCreate, u=Depends(user_dep)):
        c=db(); owned_application(c,body.application_id,u)
        if body.deadline:
            try: date.fromisoformat(body.deadline)
            except ValueError: raise err("invalid_date", "deadline must use YYYY-MM-DD", 422)
        rid=str(uuid.uuid4())
        try:
            c.execute("INSERT INTO scholarship_renewals(id,application_id,student_id,academic_year,deadline,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (rid,body.application_id,u["id"],body.academic_year,body.deadline,body.status,body.notes,now(),now())); c.commit()
        except Exception as ex:
            if "UNIQUE" in str(ex): raise err("duplicate_renewal", "A renewal already exists for this application and academic year", 409)
            raise
        return dict(c.execute("SELECT * FROM scholarship_renewals WHERE id=?",(rid,)).fetchone())

    @app.get("/api/renewals")
    def list_renewals(status: Optional[str] = None, u=Depends(user_dep)):
        if status and status not in RENEWAL_STATUSES: raise err("invalid_status", "Unsupported renewal status", 422)
        q="SELECT * FROM scholarship_renewals WHERE student_id=?"; args=[u["id"]]
        if status: q += " AND status=?"; args.append(status)
        q += " ORDER BY CASE WHEN deadline IS NULL THEN 1 ELSE 0 END, deadline"
        return [dict(r) for r in db().execute(q,args).fetchall()]

    @app.patch("/api/renewals/{renewal_id}")
    def update_renewal(renewal_id: str, body: RenewalUpdate, u=Depends(user_dep)):
        c=db(); row=c.execute("SELECT * FROM scholarship_renewals WHERE id=? AND student_id=?",(renewal_id,u["id"])).fetchone()
        if not row: raise err("not_found", "Renewal not found", 404)
        changes=body.model_dump(exclude_unset=True)
        if "deadline" in changes and changes["deadline"]:
            try: date.fromisoformat(changes["deadline"])
            except ValueError: raise err("invalid_date", "deadline must use YYYY-MM-DD", 422)
        merged={k:row[k] for k in ["deadline","status","notes"]}; merged.update(changes)
        c.execute("UPDATE scholarship_renewals SET deadline=?,status=?,notes=?,updated_at=? WHERE id=? AND student_id=?",
                  (merged["deadline"],merged["status"],merged["notes"],now(),renewal_id,u["id"])); c.commit()
        return dict(c.execute("SELECT * FROM scholarship_renewals WHERE id=?",(renewal_id,)).fetchone())

    @app.get("/api/renewals/due")
    def due_renewals(days: int = 30, u=Depends(user_dep)):
        if days < 0 or days > 365: raise err("invalid_range", "days must be between 0 and 365", 422)
        today=date.today(); cutoff=today.fromordinal(today.toordinal()+days)
        rows=db().execute("SELECT * FROM scholarship_renewals WHERE student_id=? AND deadline IS NOT NULL AND status NOT IN ('Renewed','Not_Continuing','Expired') ORDER BY deadline",(u["id"],)).fetchall()
        out=[]
        for r in rows:
            try: due=date.fromisoformat(r["deadline"])
            except ValueError: continue
            if today <= due <= cutoff: out.append(dict(r))
        return {"as_of":today.isoformat(),"window_days":days,"renewals":out,"note":"This endpoint lists due renewals; it does not send notifications."}
