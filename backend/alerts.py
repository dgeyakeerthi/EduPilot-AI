"""Personalised new-scholarship alerts and scheduled deadline/renewal reminders.

Only records already present in the application's scholarship catalogue are considered.
Newly ingested records enter the catalogue only after the existing human-verification workflow.
External delivery requires explicit per-channel consent and provider configuration.
"""
import json, os, uuid
from datetime import date, datetime, timezone
from fastapi import Depends
from backend import scheduler
from backend.integrations import mailer, messaging

CHANNELS = ("email", "sms", "whatsapp", "push")

def setup(app, user, db, err, now, scholarships, eligibility):
    def conn():
        c = db()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS scholarship_alert_state(
          student_id TEXT NOT NULL, scholarship_id TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(student_id, scholarship_id));
        CREATE TABLE IF NOT EXISTS notifications(
          id TEXT PRIMARY KEY, student_id TEXT, dedup TEXT, data TEXT,
          is_read INT DEFAULT 0, UNIQUE(student_id,dedup));
        CREATE TABLE IF NOT EXISTS prefs(student_id TEXT PRIMARY KEY,data TEXT);
        """)
        return c

    def preferences(c, sid):
        row = c.execute("SELECT data FROM prefs WHERE student_id=?", (sid,)).fetchone()
        return json.loads(row["data"]) if row else {"channels": {}, "consent": {}, "quiet_start": None, "quiet_end": None}

    def in_quiet(p):
        a,b = p.get("quiet_start"), p.get("quiet_end")
        if not a or not b: return False
        t = datetime.now().strftime("%H:%M")
        return (a <= t < b) if a <= b else (t >= a or t < b)

    def deliver(c, student, p, title, message):
        result = {"in_app": "delivered"}
        if in_quiet(p): return {**result, "external": "deferred_quiet_hours"}
        profile = json.loads(student["profile"] or "{}")
        phone = profile.get("phone_number")
        for ch in CHANNELS:
            if not p.get("channels", {}).get(ch) or not p.get("consent", {}).get(ch): continue
            if ch == "email": result[ch] = mailer.send(student["email"], title, message)
            elif ch == "sms": result[ch] = messaging.sms(phone, f"{title}: {message}")
            elif ch == "whatsapp": result[ch] = messaging.whatsapp(phone, f"{title}: {message}")
            elif ch == "push": result[ch] = messaging.push(p.get("push_subscription"), title)
        return result

    def create_alert(c, student, scholarship, assessment, kind="new_scholarship"):
        sid, kid = student["id"], scholarship["scholarship_id"]
        dedup = f"{kind}:{kid}"
        if c.execute("SELECT 1 FROM notifications WHERE student_id=? AND dedup=?", (sid,dedup)).fetchone(): return False
        status = assessment.get("eligibility_status", "more_information_required")
        title = f"New scholarship: {scholarship['scholarship_name']}"
        msg = (f"This opportunity may match your profile (assessment: {status}). "
               f"Deadline: {scholarship.get('closing_date') or 'not specified'}. "
               "Review the eligibility conditions and official source before applying.")
        p = preferences(c, sid)
        data = {"kind": kind, "title": title, "message": msg, "scholarship_id": kid,
                "official_source_url": scholarship.get("official_source_url"),
                "eligibility_status": status, "created_at": now(),
                "delivery": deliver(c, student, p, title, msg)}
        c.execute("INSERT OR IGNORE INTO notifications(id,student_id,dedup,data) VALUES(?,?,?,?)",
                  (str(uuid.uuid4()), sid, dedup, json.dumps(data)))
        c.execute("INSERT OR IGNORE INTO scholarship_alert_state VALUES(?,?,?)", (sid,kid,now()))
        return True

    def scan_new():
        c = conn(); students = c.execute("SELECT * FROM students WHERE role='student' AND email_verified=1").fetchall()
        made = 0
        for s in scholarships:
            # Only human-verified or preloaded records enter the catalogue; demo records are visibly labelled.
            if s.get("verification_status") not in ("Human_Verified", "Verified_Official") and not s.get("is_demo", False):
                continue
            for student in students:
                p = json.loads(student["profile"] or "{}")
                try: assessment = eligibility.assess(s, p)
                except Exception: continue
                if assessment.get("eligibility_status") == "not_eligible": continue
                if create_alert(c, student, s, assessment): made += 1
        c.commit()
        return f"personalised scholarship alerts created: {made}"

    def scan_reminders():
        c = conn(); today = date.today(); made = 0
        students = c.execute("SELECT * FROM students WHERE role='student' AND email_verified=1").fetchall()
        for student in students:
            p = preferences(c, student["id"])
            # Saved scholarships are stored by the existing Stage 7 feature.
            saved = c.execute("SELECT scholarship_id FROM saved WHERE student_id=?", (student["id"],)).fetchall()
            for row in saved:
                s = next((x for x in scholarships if x.get("scholarship_id")==row["scholarship_id"]), None)
                if not s or not s.get("closing_date"): continue
                try: days = (date.fromisoformat(s["closing_date"]) - today).days
                except ValueError: continue
                if days not in (7,3,1): continue
                dedup = f"deadline:{s['scholarship_id']}:{days}:{today.year}"
                if c.execute("SELECT 1 FROM notifications WHERE student_id=? AND dedup=?", (student["id"],dedup)).fetchone(): continue
                title = f"{s['scholarship_name']} closes in {days} day(s)"
                msg = f"Your saved scholarship deadline is {s['closing_date']}. Check the official source for current details."
                data = {"kind":"deadline_reminder", "title":title, "message":msg,
                        "scholarship_id":s["scholarship_id"], "official_source_url":s.get("official_source_url"),
                        "created_at":now(), "delivery":deliver(c,student,p,title,msg)}
                c.execute("INSERT OR IGNORE INTO notifications(id,student_id,dedup,data) VALUES(?,?,?,?)",
                          (str(uuid.uuid4()),student["id"],dedup,json.dumps(data))); made += 1
            # Renewal reminders derive only from the student's recorded renewal date.
            rows = c.execute("SELECT id,scholarship_id,status,data FROM applications WHERE student_id=?", (student["id"],)).fetchall()
            for approw in rows:
                data0 = json.loads(approw["data"] or "{}")
                due = data0.get("renewal_due_date")
                if not due: continue
                try: days = (date.fromisoformat(due)-today).days
                except ValueError: continue
                if days not in (30,7,3,1): continue
                dedup=f"renewal:{approw['id']}:{due}:{days}"
                if c.execute("SELECT 1 FROM notifications WHERE student_id=? AND dedup=?",(student["id"],dedup)).fetchone(): continue
                sname=next((x.get("scholarship_name") for x in scholarships if x.get("scholarship_id")==approw["scholarship_id"]),"Your scholarship")
                title=f"Renewal reminder: {sname}"
                msg=f"Your recorded renewal date is {due} ({days} day(s) remaining). Confirm requirements with the official provider."
                payload={"kind":"renewal_reminder","title":title,"message":msg,"application_id":approw["id"],"created_at":now(),"delivery":deliver(c,student,p,title,msg)}
                c.execute("INSERT OR IGNORE INTO notifications(id,student_id,dedup,data) VALUES(?,?,?,?)",(str(uuid.uuid4()),student["id"],dedup,json.dumps(payload))); made+=1
        c.commit(); return f"deadline and renewal reminders created: {made}"

    @app.post("/api/notifications/check")
    def check(u=Depends(user)):
        c=conn(); student=c.execute("SELECT * FROM students WHERE id=?",(u["id"],)).fetchone()
        # On-demand check is student-scoped and idempotent.
        n=0
        for s in scholarships:
            if s.get("verification_status") not in ("Human_Verified","Verified_Official") and not s.get("is_demo",False): continue
            a=eligibility.assess(s,json.loads(student["profile"] or "{}"))
            if a.get("eligibility_status") != "not_eligible" and create_alert(c,student,s,a): n+=1
        c.commit(); return {"created":n,"message":"Checked available verified catalogue entries; alerts are personalised and deduplicated."}

    scheduler.register("personalised_new_scholarship_alerts", int(os.environ.get("SCHOLARSHIP_ALERT_INTERVAL_MIN","10"))*60, scan_new)
    scheduler.register("deadline_and_renewal_alerts", int(os.environ.get("REMINDER_INTERVAL_MIN","60"))*60, scan_reminders)
