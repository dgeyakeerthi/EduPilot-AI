"""Playwright portal assistant. Safety: needs explicit approval, allow-listed portals only, stops at OTP/CAPTCHA/payment/declarations,
never retries a submit, records Submitted ONLY when the portal's own confirmation text matches the adapter pattern."""
import json, os, re, threading, uuid
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse
from fastapi import Depends
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
headless = lambda: os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
CAPTCHA = "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], .g-recaptcha, .h-captcha"
OTP = "input[autocomplete='one-time-code'], input[name*='otp' i]"

def portals():
    p = Path(os.environ.get("PORTALS_FILE", ROOT / "backend/sample_data/portals.json")); return json.loads(p.read_text()) if p.exists() else {}
def adapter_for(url):
    u = urlparse(url or "")
    if u.scheme != "https" or not u.hostname: return None
    for k, a in portals().items():
        if a.get("enabled") and u.hostname in a["hosts"]: return {**a, "key": k}
def detect(pg, ad):
    for name, sel in (ad.get("stop_selectors") or {}).items():
        if pg.query_selector(sel): return name
    if pg.query_selector(CAPTCHA): return "captcha"
    if pg.query_selector(OTP): return "otp"
    return None

class Start(BaseModel): mode: Literal["assist", "submit"]; portal_url: Optional[str] = Field(None, pattern=r"^https://\S+$", max_length=500)

def drive(ad, values, mode, L):
    from playwright.sync_api import sync_playwright
    ok_host = lambda pg: urlparse(pg.url).hostname in ad["hosts"]
    with sync_playwright() as p:
        b = p.chromium.launch(headless=headless()); pg = b.new_page(); pg.set_default_timeout(15000)
        try:
            pg.goto(ad["start_url"])
            if not ok_host(pg): return "Blocked", "Redirected away from the allowed portal host", None
            if (s := detect(pg, ad)): return "Needs_Student", f"{s} step found. Complete it yourself; automation will not bypass it.", None
            for f, sel in ad["field_map"].items():
                if values.get(f) not in (None, ""): pg.fill(sel, str(values[f])); L(f"filled {f}")
            if mode == "assist":
                L("Fields filled. Finish in the open browser window (documents, OTP, CAPTCHA, declarations, submit). Close it when done.")
                pg.wait_for_event("close", timeout=0); return "Assist_Completed", "Browser closed by student. Report the outcome via the status update endpoint.", None
            if not ok_host(pg): return "Blocked", "Left the allowed portal host", None
            if (s := detect(pg, ad)): return "Needs_Student", f"{s} must be completed by you before submission.", None
            pg.click(ad["submit_selector"])  # single attempt, never retried
            try:
                pg.wait_for_selector(ad["confirmation_selector"], timeout=30000)
                m = re.search(ad["confirmation_pattern"], pg.inner_text(ad["confirmation_selector"]))
            except Exception: m = None
            if m: return "Submitted", "Portal showed a confirmation", (m.group(1) if m.groups() else m.group(0))
            return "Submission_Uncertain", "Clicked submit but no confirmation was found. Check the portal before doing anything else; do not resubmit blindly.", None
        except Exception as e:
            return "Failed", f"{type(e).__name__} before completion", None
        finally:
            try: b.close()
            except Exception: pass

def setup(app, user, db, err, now, sch, el):
    def tdb():
        c = db(); c.executescript("CREATE TABLE IF NOT EXISTS automation_runs(id TEXT PRIMARY KEY,application_id TEXT,mode TEXT,status TEXT,detail TEXT,log TEXT DEFAULT '[]',created_at TEXT);"); return c
    def finish(rid, aid, status, detail, ref):
        c = tdb(); c.execute("UPDATE automation_runs SET status=?,detail=? WHERE id=?", (status, detail, rid))
        r = c.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone(); d = json.loads(r["data"]); st = r["status"]
        if status == "Submitted": st, d["provider_reference"] = "Submitted", ref
        tl = json.loads(r["timeline"]) + [{"event": f"Browser automation: {status} - {detail}", "event_source": "Browser_Automation",
              "verification_status": "Provider_Confirmed_Page_Text" if status == "Submitted" else "Unverified", "recorded_at": now()}]
        c.execute("UPDATE applications SET status=?,data=?,timeline=? WHERE id=?", (st, json.dumps(d), json.dumps(tl), aid)); c.commit()
    def work(rid, aid, ad, mode, values):
        log = []
        def L(m): log.append({"at": now(), "msg": m}); c = tdb(); c.execute("UPDATE automation_runs SET log=? WHERE id=?", (json.dumps(log), rid)); c.commit()
        try: status, detail, ref = drive(ad, values, mode, L)
        except Exception as e: status, detail, ref = "Failed", type(e).__name__, None
        finish(rid, aid, status, detail, ref)

    @app.post("/api/applications/{aid}/automation/start", status_code=202)
    def start(aid: str, b: Start, u=Depends(user)):
        c = tdb(); r = c.execute("SELECT * FROM applications WHERE id=? AND student_id=?", (aid, u["id"])).fetchone()
        if not r: raise err("not_found", "Application not found", 404)
        if r["status"] != "Awaiting_Approval" or not r["approved"]: raise err("approval_required", "Explicit student approval is required before any portal automation", 409)
        ad = adapter_for(b.portal_url or sch(r["scholarship_id"]).get("application_url"))
        if not ad: raise err("unsupported_portal", "No enabled adapter for this portal. Use guided manual completion.", 409)
        try: import playwright.sync_api  # noqa
        except ImportError: raise err("playwright_not_installed", "Run: pip install playwright && playwright install chromium", 501)
        if b.mode == "assist" and headless(): raise err("needs_visible_browser", "Set PLAYWRIGHT_HEADLESS=false and run on your own machine for assist mode", 409)
        if c.execute("SELECT 1 FROM automation_runs WHERE application_id=? AND status IN ('Running','Submission_Uncertain')", (aid,)).fetchone():
            raise err("run_exists", "A run is active or its result is uncertain; check the portal first", 409)
        d = json.loads(r["data"]); values = {**{k: v["value"] for k, v in d["form_fields"].items()}, **d["answers"]}
        rid = str(uuid.uuid4()); c.execute("INSERT INTO automation_runs(id,application_id,mode,status,detail,created_at) VALUES(?,?,?,?,?,?)", (rid, aid, b.mode, "Running", "", now())); c.commit()
        threading.Thread(target=work, args=(rid, aid, ad, b.mode, values), daemon=True).start()
        return {"run_id": rid, "status": "Running", "portal": ad["key"]}

    @app.get("/api/applications/{aid}/automation/runs")
    def runs(aid: str, u=Depends(user)):
        c = tdb()
        if not c.execute("SELECT 1 FROM applications WHERE id=? AND student_id=?", (aid, u["id"])).fetchone(): raise err("not_found", "Application not found", 404)
        return [{**dict(r), "log": json.loads(r["log"])} for r in c.execute("SELECT * FROM automation_runs WHERE application_id=? ORDER BY created_at DESC", (aid,))]
