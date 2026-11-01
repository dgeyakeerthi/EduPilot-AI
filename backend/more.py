import csv, io, json, uuid
from datetime import date
from typing import Optional, Literal
from fastapi import Depends, Response
from pydantic import BaseModel, Field

CH = ["email", "sms", "whatsapp", "push"]
class Prefs(BaseModel):
    channels: dict[str, bool] = {}; consent: dict[str, bool] = {}
    push_subscription: Optional[dict] = None
    quiet_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$"); quiet_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
class Update(BaseModel):
    status: Literal["Submitted", "Under_Review", "Approved", "Rejected", "Withdrawn"]
    note: str = Field(min_length=3, max_length=500)
class Pay(BaseModel): payment_status: Literal["Not_Applicable", "Pending", "Received", "Delayed", "Failed"]
class Renew(BaseModel): renewal_due_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

def quiet(pr):
    from datetime import datetime
    a, b, t = pr.get("quiet_start"), pr.get("quiet_end"), datetime.now().strftime("%H:%M")
    return bool(a and b) and ((a <= t < b) if a <= b else (t >= a or t < b))
def delivery(pr, u, title):
    from backend.integrations import mailer, messaging as m
    ph = json.loads(u["profile"]).get("phone_number")
    f = {"email": lambda: mailer.send(u["email"], title, title), "sms": lambda: m.sms(ph, title), "whatsapp": lambda: m.whatsapp(ph, title), "push": lambda: m.push(pr.get("push_subscription"), title)}
    return {ch: ("disabled" if not on else f[ch]()) for ch, on in pr["channels"].items()}

def safe(v):  # CSV formula-injection guard
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in "=+-@\t\r" else v

def setup(app, user, db, err, now, SCH, sch, el):
    def tdb():
        c = db(); c.executescript("""CREATE TABLE IF NOT EXISTS saved(student_id TEXT,scholarship_id TEXT,PRIMARY KEY(student_id,scholarship_id));
        CREATE TABLE IF NOT EXISTS prefs(student_id TEXT PRIMARY KEY,data TEXT);
        CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,student_id TEXT,dedup TEXT,data TEXT,is_read INT DEFAULT 0,UNIQUE(student_id,dedup));"""); return c
    def myapp(c, aid, u):
        r = c.execute("SELECT * FROM applications WHERE id=? AND student_id=?", (aid, u["id"])).fetchone()
        if not r: raise err("not_found", "Application not found", 404)
        return r
    def write(c, r, status, d, ev):
        tl = json.loads(r["timeline"]) + [{"event": ev, "event_source": "Student_Update", "verification_status": "Unverified", "recorded_at": now()}]
        c.execute("UPDATE applications SET status=?,data=?,timeline=? WHERE id=?", (status, json.dumps(d), json.dumps(tl), r["id"])); c.commit()

    @app.post("/api/saved/{sid}", status_code=201)
    def save(sid: str, u=Depends(user)): sch(sid); c = tdb(); c.execute("INSERT OR IGNORE INTO saved VALUES(?,?)", (u["id"], sid)); c.commit(); return {"saved": True}
    @app.delete("/api/saved/{sid}")
    def unsave(sid: str, u=Depends(user)): c = tdb(); c.execute("DELETE FROM saved WHERE student_id=? AND scholarship_id=?", (u["id"], sid)); c.commit(); return {"saved": False}
    @app.get("/api/saved")
    def saved(u=Depends(user)): return [sch(r["scholarship_id"]) for r in tdb().execute("SELECT * FROM saved WHERE student_id=?", (u["id"],))]

    @app.get("/api/compare")
    def compare(ids: str, u=Depends(user)):
        L = [sch(i) for i in ids.split(",") if i]
        if not 2 <= len(L) <= 3: raise err("invalid_compare", "Choose 2 or 3 scholarships", 422)
        return [{"scholarship_id": s["scholarship_id"], "name": s["scholarship_name"], "provider": s["provider_name"], "benefit": f'{s["benefit_amount"]} {s["currency"]} ({s["benefit_frequency"]})',
                 "closing_date": s["closing_date"], "status": el.status(s), "required_documents": s["required_documents"], "verification_status": s["verification_status"], "renewal_available": s["renewal_available"]} for s in L]

    @app.get("/api/notifications/preferences")
    def getp(u=Depends(user)):
        r = tdb().execute("SELECT data FROM prefs WHERE student_id=?", (u["id"],)).fetchone()
        return json.loads(r["data"]) if r else {"channels": {}, "consent": {}, "quiet_start": None, "quiet_end": None}
    @app.put("/api/notifications/preferences")
    def putp(b: Prefs, u=Depends(user)):
        for ch, on in b.channels.items():
            if ch not in CH: raise err("invalid_channel", f"Unknown channel {ch}", 422, {"allowed": CH})
            if on and not b.consent.get(ch): raise err("consent_required", f"Consent is required to enable {ch}", 422)
        c = tdb(); c.execute("INSERT OR REPLACE INTO prefs VALUES(?,?)", (u["id"], json.dumps(b.model_dump()))); c.commit(); return b
    @app.post("/api/notifications/generate")
    def gen(u=Depends(user)):
        c, today, made, skipped = tdb(), date.today(), 0, 0
        pr = getp(u)
        for r in c.execute("SELECT scholarship_id FROM saved WHERE student_id=?", (u["id"],)).fetchall():
            s = sch(r["scholarship_id"])
            if el.status(s) != "Open": continue
            n = (date.fromisoformat(s["closing_date"]) - today).days
            if n in (7, 3, 1):
                key = f'deadline:{s["scholarship_id"]}:{n}'
                if c.execute("SELECT 1 FROM notifications WHERE student_id=? AND dedup=?", (u["id"], key)).fetchone(): continue
                if quiet(pr) and any(pr["channels"].values()): skipped += 1; continue  # retried on a later call outside quiet hours
                d = {"kind": "deadline_reminder", "title": f'{s["scholarship_name"]} closes in {n} day(s)', "created_at": now(),
                     "delivery": {"in_app": "delivered", **delivery(pr, u, f'{s["scholarship_name"]} closes in {n} day(s)')}}  # no external provider wired
                cur = c.execute("INSERT OR IGNORE INTO notifications(id,student_id,dedup,data) VALUES(?,?,?,?)", (str(uuid.uuid4()), u["id"], f'deadline:{s["scholarship_id"]}:{n}', json.dumps(d)))
                made += cur.rowcount
        c.commit(); return {"created": made, "skipped_quiet_hours": skipped}
    @app.get("/api/notifications")
    def notes(u=Depends(user)): return [{"notification_id": r["id"], "is_read": bool(r["is_read"]), **json.loads(r["data"])} for r in tdb().execute("SELECT * FROM notifications WHERE student_id=? ORDER BY rowid DESC", (u["id"],))]
    @app.post("/api/notifications/{nid}/read")
    def read(nid: str, u=Depends(user)): c = tdb(); c.execute("UPDATE notifications SET is_read=1 WHERE id=? AND student_id=?", (nid, u["id"])); c.commit(); return {"ok": True}

    @app.post("/api/applications/{aid}/updates")
    def upd(aid: str, b: Update, u=Depends(user)):
        c = tdb(); r = myapp(c, aid, u)
        if b.status == "Submitted" and not r["approved"]: raise err("approval_required", "Cannot record Submitted before your approval", 409)
        d = json.loads(r["data"]); d["last_reported_note"] = b.note
        write(c, r, b.status, d, f"Student reported: {b.status} ({b.note})")
        return {"application_status": b.status, "event_source": "Student_Update", "verification_status": "Unverified", "note": "Student-reported, not confirmed by the provider."}
    @app.post("/api/applications/{aid}/payment")
    def pay(aid: str, b: Pay, u=Depends(user)):
        c = tdb(); r = myapp(c, aid, u); d = json.loads(r["data"]); d["payment_status"] = b.payment_status
        write(c, r, r["status"], d, f"Payment status (student-reported): {b.payment_status}"); return {"payment_status": b.payment_status, "verification_status": "Unverified"}
    @app.put("/api/applications/{aid}/renewal")
    def renew(aid: str, b: Renew, u=Depends(user)):
        c = tdb(); r = myapp(c, aid, u)
        if not sch(r["scholarship_id"])["renewal_available"]: raise err("no_renewal", "This scholarship has no renewal", 409)
        d = json.loads(r["data"]); d["renewal_due_date"] = b.renewal_due_date; write(c, r, r["status"], d, "Renewal due date set"); return d
    @app.get("/api/exports/applications.csv")
    def export(u=Depends(user)):
        o = io.StringIO(); w = csv.writer(o); w.writerow(["application_id", "scholarship", "status", "approved", "payment_status"])
        for r in tdb().execute("SELECT * FROM applications WHERE student_id=?", (u["id"],)):
            w.writerow([safe(r["id"]), safe(sch(r["scholarship_id"])["scholarship_name"]), safe(r["status"]), bool(r["approved"]), safe(json.loads(r["data"]).get("payment_status"))])
        return Response(o.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=applications.csv"})

    @app.get("/api/admin/dashboard")
    def dash(u=Depends(user)):
        if u["role"] != "admin": raise err("forbidden", "Administrator access required", 403)
        c = tdb(); q = lambda s: [dict(r) for r in c.execute(s)]
        return {"students": q("SELECT COUNT(*) n FROM students WHERE role='student'")[0]["n"], "applications_by_status": q("SELECT status, COUNT(*) n FROM applications GROUP BY status"),
                "reports_by_status": q("SELECT status, COUNT(*) n FROM reports GROUP BY status") if c.execute("SELECT name FROM sqlite_master WHERE name='reports'").fetchone() else [],
                "scholarships": len(SCH), "ai": {"gemini": "see /api/health", "note": "AI usage/cost tracking not yet implemented"}}

    def run_all():
        import os; n = 0
        for r in tdb().execute("SELECT * FROM students WHERE role='student' AND email_verified=1").fetchall():
            try: n += gen(r)["created"]
            except Exception: pass
        return f"{n} reminders created"
    import os; from backend import scheduler
    scheduler.register("reminders", int(os.environ.get("REMINDER_INTERVAL_MIN", "60")) * 60, run_all)
