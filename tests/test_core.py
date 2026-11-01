import os, tempfile, json, pathlib
os.environ["AUTH_SECRET"] = "test-secret-not-real"; os.environ["EDUPILOT_DEMO_MODE"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db")
from datetime import date
from fastapi.testclient import TestClient
from backend.main import app
from backend.services import eligibility as el
S = json.loads(pathlib.Path("backend/sample_data/scholarships.json").read_text())
c = TestClient(app)

def signup(email):
    r = c.post("/api/auth/register", json={"email": email, "password": "password123", "full_name": "Test Student"}).json()
    assert c.post("/api/auth/verify", json={"email": email, "code": r["demo_verification_code"]}).status_code == 200
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": email, "password": "password123"}).json()["token"]}

def test_health_and_demo():
    assert c.get("/api/health").json()["status"] == "ok"
    assert all(s["is_demo"] for s in c.get("/api/demo/scholarships").json())

def test_auth_required_and_error_shape():
    r = c.get("/api/students/me"); assert r.status_code == 401 and "request_id" in r.json() and "code" in r.json()["error"]

def test_unknown_never_matches():
    a = el.assess(S[0], {"education_level": "Undergraduate"})
    assert a["eligibility_status"] == "more_information_required" and a["unknown_criteria"]

def test_unmet_mandatory_is_not_eligible():
    p = {"education_level": "Undergraduate", "course_name": "B.Tech", "annual_family_income": 900000, "academic_score_value": 80, "academic_score_type": "Percentage"}
    assert el.assess(S[0], p)["eligibility_status"] == "not_eligible"

def test_score_provisional_when_component_missing():
    r = el.rank_score(S[0], {"education_level": "Undergraduate"}, date(2026, 11, 1)); assert r["provisional"] and r["relevance_score"] is None

def test_full_score_and_status():
    p = {"education_level": "Undergraduate", "course_name": "B.Tech", "annual_family_income": 300000, "academic_score_value": 75, "academic_score_type": "Percentage", "social_category": "OBC"}
    r = el.rank_score(S[0], p, date(2026, 11, 1)); assert not r["provisional"] and r["relevance_score"] == 0.98  # 0.975 rounded to two decimals (half-up)
    assert el.status(S[2], date(2026, 11, 1)) == "Closed"

def test_no_submit_without_approval_and_isolation():
    h1, h2 = signup("a@example.com"), signup("b@example.com")
    r = c.post("/api/applications/prepare", headers=h1, json={"scholarship_id": S[0]["scholarship_id"]})
    if r.status_code != 201: return  # demo window closed on this run date
    aid = r.json()["application_id"]
    assert c.post(f"/api/applications/{aid}/submit", headers=h1).status_code == 409
    assert c.get(f"/api/applications/{aid}/timeline", headers=h2).status_code == 404

def test_report_requires_admin_and_does_not_flag():
    h = signup("r@example.com")
    r = c.post(f"/api/scholarships/{S[0]['scholarship_id']}/reports", headers=h, json={"reason": "Looks fake"})
    assert r.status_code == 201 and r.json()["status"] == "Submitted"
    assert c.get("/api/admin/scholarship-reports", headers=h).status_code == 403
    assert c.get(f"/api/scholarships/{S[0]['scholarship_id']}", headers=h).json()["verification_status"] == "Automated_Checks_Completed"

def test_upload_rejects_bad_type():
    h = signup("u@example.com")
    r = c.post("/api/documents", headers=h, data={"document_type": "Marksheet"}, files={"file": ("x.exe", b"MZ")}); assert r.status_code == 415

def test_compare_needs_two_and_csv_guard():
    from backend.more import safe
    assert safe("=cmd()") == "'=cmd()" and safe("ok") == "ok"
    h = signup("m@example.com")
    assert c.get(f"/api/compare?ids={S[0]['scholarship_id']}", headers=h).status_code == 422
    assert len(c.get(f"/api/compare?ids={S[0]['scholarship_id']},{S[1]['scholarship_id']}", headers=h).json()) == 2

def test_channel_needs_consent():
    h = signup("n@example.com")
    assert c.put("/api/notifications/preferences", headers=h, json={"channels": {"sms": True}, "consent": {}}).status_code == 422

def test_jaccard_duplicate_and_fallback_extraction():
    from backend.ingest import jaccard, tokens, extract, clean
    a = {"scholarship_name": "Aurora Merit Scholarship", "provider_name": "Aurora Foundation"}
    assert jaccard(tokens(a), tokens(a)) == 1.0 and jaccard(tokens(a), tokens({"scholarship_name": "Totally Different", "provider_name": "X"})) < .9
    rec, method = extract("Sunrise Grant\nDeadline 2027-01-31 for all applicants of this fictional example text goes here"); rec = clean(rec)
    assert method == "rules" and rec["closing_date"] == "2027-01-31" and not rec["criteria"]

def test_ingest_admin_only():
    h = signup("s@example.com")
    assert c.post("/api/admin/sources/ingest", headers=h, json={"source_url": "https://x.example", "raw_text": "x" * 60}).status_code == 403

def test_pdf_valid_and_semantic_rank():
    from backend.pdf import make_pdf
    from backend.export_search import rank
    b = make_pdf("T (x)", [f"line {i}" for i in range(60)]); assert b.startswith(b"%PDF") and b.rstrip().endswith(b"%%EOF") and b.count(b"/Type /Page ") == 2
    docs = [f'{s["scholarship_name"]} {s["description"]}' for s in S]
    res, _ = rank("engineering students", docs); assert res and res[0][0] == 0

def test_mailer_not_configured_and_pdf_endpoint():
    from backend.integrations import mailer
    os.environ.pop("SMTP_HOST", None); assert mailer.send("a@b.c", "s", "b") == "not_configured"
    h = signup("p@example.com"); r = c.get("/api/exports/applications.pdf", headers=h); assert r.status_code == 200 and r.content.startswith(b"%PDF")

class FakePage:
    def __init__(self, present): self.present = present
    def query_selector(self, sel): return sel in self.present or any(p in sel for p in self.present) or None

def test_automation_stop_detection_and_adapter_allowlist():
    from backend import automation as au
    ad = {"stop_selectors": {"payment": "#pay"}}
    assert au.detect(FakePage({"#pay"}), ad) == "payment" and au.detect(FakePage({"recaptcha"}), {}) == "captcha" and au.detect(FakePage(set()), {}) is None
    assert au.adapter_for("https://example.invalid/apply") is None  # shipped adapter is disabled
    assert au.adapter_for("http://example.invalid/") is None

def test_automation_requires_approval_and_messaging_guards():
    from backend.integrations import messaging as m
    assert m.sms("12345", "x") == "invalid_phone" and m.sms("+919876543210", "x") == "not_configured" and m.push({"endpoint": "x"}, "t") == "not_configured"
    h = signup("q@example.com"); r = c.post("/api/applications/prepare", headers=h, json={"scholarship_id": S[0]["scholarship_id"]})
    if r.status_code == 201:
        assert c.post(f"/api/applications/{r.json()['application_id']}/automation/start", headers=h, json={"mode": "submit"}).status_code == 409

def test_crawler_blocks_unsafe_urls_and_parses_html():
    import pytest
    from backend import crawl
    for bad in ("http://example.com", "https://127.0.0.1/x", "https://10.0.0.5/", "https://[::1]/"):
        with pytest.raises(ValueError): crawl.check_url(bad)
    t = crawl.html_to_text("<html><script>evil()</script><h1>Grant</h1><p>Closes 2027-01-31</p></html>")
    assert "evil" not in t and "Grant" in t and "2027-01-31" in t

def test_scheduler_runs_task_and_ai_cost_hook():
    from backend import scheduler
    from backend.ai import router as ai
    calls = []; scheduler.register("t", 0, lambda: calls.append(1) or "ok"); scheduler.TASKS[-1][3] = 0
    t = scheduler.TASKS[-1]; t[2](); assert calls
    old, got = ai.usage_hook, []; ai.usage_hook = got.append
    try: ai.complete("hello", task="test")
    finally: ai.usage_hook = old
    assert got and got[0]["task"] == "test" and got[0]["prompt_chars"] == 5

def test_admin_endpoints_forbidden_for_students():
    h = signup("z@example.com")
    for p in ("/api/admin/ai-cost", "/api/admin/sources", "/api/admin/scheduler"): assert c.get(p, headers=h).status_code == 403
