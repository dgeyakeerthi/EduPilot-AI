# EduPilot AI — Final Deployment and Acceptance Checklist

This is a deployment checklist for the integrated MVP. Passing it does not certify legal compliance, production security, provider approval, or universal scholarship-portal compatibility.

## 1. Before deployment
- [ ] Choose a host and region suitable for Indian student data and review applicable privacy/legal obligations.
- [ ] Use a managed production database or a persistent encrypted volume. Do not deploy SQLite on an ephemeral filesystem or share one SQLite file across multiple app replicas.
- [ ] Generate `AUTH_SECRET` with at least 32 random bytes; store it in the host's secret manager, never in source control.
- [ ] Configure `DATABASE_URL`, `APP_BASE_URL`, `FRONTEND_BASE_URL`, `ADMIN_EMAILS` and `DOCUMENT_STORAGE_DIR`.
- [ ] Configure HTTPS at the trusted reverse proxy; set `EDUPILOT_HTTPS_TERMINATED=true` only when HTTPS is actually enforced.
- [ ] Configure restrictive CORS at the deployment gateway if the frontend is served from a separate origin.
- [ ] Keep `EDUPILOT_DEMO_MODE=false` in production.
- [ ] Set `SCHEDULER_ENABLED=false` when running multiple replicas; run scheduled jobs through one dedicated worker/cron instead.
- [ ] Set `RATE_LIMIT_ENABLED=true` only as a small single-process safeguard. Production rate limiting must be enforced by a shared gateway/WAF.
- [ ] Configure private object storage, encryption, backups, retention and restore procedures for student documents. Local disk storage is for development/single-instance MVP only.

## 2. Optional external services
- [ ] Gemini API key and approved model IDs; verify quota, region, data-use and retention terms.
- [ ] Ollama installed and local Qwen model pulled; test RAM/latency on the target machine.
- [ ] Nomic embedding model installed locally; rebuild/verify the index after model changes.
- [ ] Tesseract executable on PATH; test scanned PDFs and image uploads. OCR output must be reviewed by the student.
- [ ] SMTP/SMS/WhatsApp/push provider credentials and consent flows; send test messages only to opted-in test accounts.
- [ ] Configure official scholarship sources individually; check their terms, robots rules, rate limits and source ownership. Keep uncertain extraction in human review.
- [ ] Configure and test provider-specific portal adapters only where permitted. Never bypass login protections, OTP, CAPTCHA, biometrics, declarations or payment controls.

## 3. Security and privacy acceptance
- [ ] Confirm student A cannot read/update student B's profile, documents, applications, RAG context, notifications or handoff sessions.
- [ ] Confirm admin endpoints reject non-admin accounts.
- [ ] Confirm no API key, password, OTP, bank detail or secret appears in logs, frontend bundles, exports or AI prompts unnecessarily.
- [ ] Confirm document access is authenticated and storage is not web-public.
- [ ] Confirm account deletion/export and retention behaviour against the applicable legal policy before enabling real users.
- [ ] Review audit logs and configure monitoring/alerting for auth failures, admin actions, crawler errors and background job failures.
- [ ] Perform dependency scanning, secret scanning, penetration testing and backup-restore testing before a public launch.

## 4. Functional acceptance
- [ ] Register, verify email and log in with a non-demo account.
- [ ] Complete profile and confirm missing-field prompts.
- [ ] Search, save and compare scholarships; verify every live record's source and last-verified date.
- [ ] Run eligibility checks and verify unknown mandatory criteria are never treated as matched.
- [ ] Upload, review, correct and delete a test document; verify 20 MB limit and cross-account isolation.
- [ ] Test assistant with Gemini available, Gemini unavailable/local fallback, and all AI providers unavailable.
- [ ] Confirm document-grounded answers cite the student's own documents and private document text is not sent to cloud LLMs.
- [ ] Prepare an application, review fields, approve explicitly, and verify submission controls remain student-controlled.
- [ ] Create a guided portal handoff; confirm checkpoints are student-reported and do not assert provider submission.
- [ ] Test status, payment and renewal records; distinguish student-reported from provider-verified information.
- [ ] Test deadline alerts, consent, quiet hours, deduplication and each configured delivery channel.
- [ ] Test source ingestion, duplicate/version handling, admin review and explicit publish decision.
- [ ] Test student/admin dashboards and CSV export formula-injection handling.

## 5. Run and verify

Development startup (Windows PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:AUTH_SECRET = (python -c "import secrets; print(secrets.token_hex(32))")
python -m compileall -q backend tests
pytest -q
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
python scripts/run_smoke_checks.py http://127.0.0.1:8000
```

For production, run behind a managed HTTPS reverse proxy and use the host's secret manager. Do not use `--reload` in production. Configure a single scheduler worker or an external scheduler; do not run duplicate schedulers in every replica.

## 6. Known MVP boundaries
- Sample scholarship records are fictional/demo data until replaced with reviewed, sourced records.
- A source registry/crawler does not mean every Indian scholarship provider is already connected.
- External provider credentials, quotas, live endpoints and model availability must be verified in the deployment environment.
- Portal handoff is guided unless a provider-specific adapter is separately built, authorised and tested.
- In-process rate limiting and scheduler are not multi-instance production infrastructure.
- Readiness checks validate only local essentials; they do not certify external providers or end-to-end functionality.
