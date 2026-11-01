# EduPilot AI (MVP core)
Implements a first slice of the spec: auth, profile + completeness, fictional demo scholarships, deterministic eligibility,
ranking (`0.40E+0.25C+0.15A+0.10D+0.10T`, Provisional when incomplete), application prep, explicit approval gate, timeline.
## Run
```
pip install -r requirements.txt
export AUTH_SECRET=$(python -c "import secrets;print(secrets.token_hex(32))")
export EDUPILOT_DEMO_MODE=true   # shows verification code on register (no email provider yet)
uvicorn backend.main:app --reload   # open http://localhost:8000
```
## Test
`AUTH_SECRET=x pytest -q`
## Known limitations / not yet built
Added since v1: document upload/vault (type/size/magic-byte checks, local PDF text via PyMuPDF if installed; scanned-image OCR needs Tesseract, not bundled), suspicious-report + admin review + audit log (set ADMIN_EMAILS), calendar with 7/3/1-day reminders, AI router (Gemini capped -> Ollama Qwen3 -> deterministic fallback; set model IDs in env after verifying them).
Still not built: real source discovery/extraction, embeddings/FAISS, browser automation, email/SMS/push delivery, renewals/payments/tracking integrations, admin dashboard UI, PDF/CSV export, Hindi/Telugu UI, frontend screens for documents/calendar/assistant. Nothing here has been executed yet (no network in the build sandbox).
`/submit` never marks `Submitted`: no portal integration exists, so it returns guided-manual instructions.
Scholarship data is fictional sample data (`backend/sample_data`), labelled `[DEMO]`. Model IDs in the spec should be verified before wiring AI.

## v3 additions
Saved scholarships + compare, notification preferences (consent-gated) and in-app deadline reminders with dedup (email/SMS/WhatsApp/push report `not_configured`: no provider wired), student-reported tracking + payment updates (always labelled Unverified), renewals, CSV export (formula-injection safe), admin dashboard counts, and frontend screens for documents, deadlines, notifications and the assistant.
Still not built: real source discovery/extraction, FAISS embeddings, browser automation, provider email/SMS delivery, AI usage/cost tracking, admin UI, PDF export, Hindi/Telugu UI.

## v4 additions
Admin-assisted ingestion (`/api/admin/sources/ingest`: LLM-or-rules extraction, Jaccard>=0.90 duplicate flags, provenance, mandatory human publish; nothing auto-publishes), `frontend/admin.html`, in-memory AI usage endpoint, English/Hindi/Telugu labels for main headings and buttons (have a native speaker review wording; error messages and data stay English).
Still not built: automatic crawling/fetching of live sources, FAISS embeddings, browser automation, real email/SMS delivery, PDF export, persistent AI cost tracking.

## v5 additions
SMTP email (verification codes + deadline reminders; set SMTP_* in env, retries 1/2/4s, reports `not_configured` otherwise; quiet hours defer generation until the next call outside the window), dependency-free PDF export, semantic search (`/api/search/semantic`: Ollama embeddings if EMBED_MODEL is set, else a local keyword-hash vector; uses FAISS automatically if `faiss-cpu` + `numpy` are installed, else plain cosine).
Optional installs: `pip install pymupdf faiss-cpu numpy pytesseract pillow`. For OCR, also install the Tesseract system executable and ensure it is on PATH. Scanned PDFs are rasterised locally and processed page-by-page; image documents use the same local OCR path. OCR text can contain errors and does not authenticate documents.
Still not built: browser automation for portals, SMS/WhatsApp/push providers, automatic crawling of live sources, persistent AI cost tracking, scheduled background reminders (reminders are generated when the student presses the button).

## v6 additions
**SMS/WhatsApp (Twilio) and Web Push (pywebpush+VAPID)** are wired into deadline reminders; set `TWILIO_*` / `VAPID_PRIVATE_KEY`, add a E.164 `phone_number` to the profile, and PUT `/api/notifications/preferences` with consent (+ `push_subscription` for push). Unset providers report `not_configured`.
**Portal assistant** (`POST /api/applications/{id}/automation/start`, mode `assist` or `submit`; `GET .../automation/runs`): install `pip install playwright pywebpush && playwright install chromium`, run on your own machine. Rules: needs explicit approval; only adapters in `backend/sample_data/portals.json` (or `PORTALS_FILE`) with `"enabled": true` and a matching https host; stops at OTP, CAPTCHA, payment, declarations; `assist` needs `PLAYWRIGHT_HEADLESS=false` and leaves final steps to you; `submit` clicks once, never retries, and records `Submitted` only when the portal's confirmation text matches the adapter's `confirmation_pattern` (otherwise `Submission_Uncertain`). **You must write and test an adapter (selectors, confirmation pattern) per real portal and respect each portal's terms of use; none ship working.**
Not built: automatic crawling of live sources, scheduled background reminders, persistent AI cost tracking, document upload automation.

## v7 additions
**Live source fetching** (admin: `/api/admin/sources`, `fetch-now`, `frontend/admin.html`): https only; private/loopback/link-local addresses and redirects to them are blocked; robots.txt respected (if robots.txt can't be read the page is skipped); 1 MB / html-or-text limits; polite delay (`CRAWL_DELAY_S`); set `CRAWLER_CONTACT`. Only changed pages are re-extracted, and results are queued as `Pending_Review` - never auto-published. Fetched text is untrusted input. Known limit: DNS can change between the safety check and the request.
**Background scheduler** (`backend/scheduler.py`, started on app startup): deadline reminders every `REMINDER_INTERVAL_MIN` (default 60; dedup + quiet hours still apply, quiet hours use server local time) and source checks every `CRAWL_CHECK_MIN`. Single process only: run one uvicorn worker (or move these to a cron job). `GET /api/admin/scheduler` shows last runs. Set `SCHEDULER_ENABLED=false` to disable.
**AI cost tracking** (`GET /api/admin/ai-cost`): every model call is persisted (provider, task, estimated tokens = chars/4, daily Gemini budget % if `AI_DAILY_TOKEN_BUDGET` is set). Costs are estimates assuming free tier / local models.
Not built: document upload via portal assistant, OCR for scanned images, cross-document consistency, guardian access, session expiry/rate limiting/password reset, full 40-test suite.


## v8 additions (this build)
- Document analysis now attempts local Tesseract OCR for image uploads and scanned PDFs when `pytesseract`, Pillow and the Tesseract executable are installed. Native PDF text extraction remains the first choice. Extraction method and a clear manual-review warning are recorded.
- Dashboard styling now uses the agreed Midnight Indigo / Electric Violet / Aqua Mint / Soft Lavender palette with responsive two-column cards. This is a styling pass, not a complete redesign matching the reference mockup.
- Corrected the ranking test to reflect the SDD weighted result 0.975 rounded to 0.98 (half-up); the implementation remains deterministic.

## Frontend milestone — Student and Admin workspaces

The frontend has been expanded into responsive student workspace views for Overview, Scholarship Explorer, Applications, Document Vault, AI Assistant, Calendar/Notifications, and Profile. The student views call the existing authenticated API endpoints; they do not fabricate records when an endpoint is unavailable. A separate `frontend/admin.html` provides an administrator console for dashboard summaries, source ingestion/review, watched sources, and student-submitted reports. The Admin console requires an authenticated account whose email is configured in `ADMIN_EMAILS`.

The current UI is implemented as static HTML/CSS/JavaScript served by FastAPI. It is **not yet a React migration**. Translation selection is currently a preference placeholder; full Hindi/Telugu translation is not implemented. The AI Assistant UI calls the existing `/api/assistant/messages` endpoint, and its capabilities are limited to what the backend currently supports. Calendar and notification views display data returned by the API; they do not guarantee external delivery.

### Frontend validation

- JavaScript syntax checked with Node.js `--check` for both student and admin pages.
- Backend tests: `PYTHONPATH=. pytest -q` — 23 passed, 2 FastAPI deprecation warnings.
- Python compilation checked for backend modules.

To run locally, follow the setup steps above, then open the application at the configured local server address. Sign in with an admin-configured account to access the Admin console.

## Stage 2 — persistent Nomic + FAISS retrieval
- Replaced the earlier per-request embedding approach with `backend/embeddings.py`, a persistent local index manager using Ollama `/api/embed` and the configured `nomic-embed-text-v2-moe` model by default.
- `/api/search/semantic` now lazily loads a matching saved index, or rebuilds it when the scholarship corpus or embedding model changes. The index stores model name, corpus fingerprint, dimension, text records and vectors. FAISS index files are used when `faiss-cpu` is installed; exact cosine retrieval is used otherwise.
- Index writes use temporary files and atomic replacement. A model change or corpus change causes a rebuild; saved vectors from another model are never reused.
- If local embeddings are unavailable, semantic search explicitly reports a lexical fallback rather than pretending keyword overlap is semantic retrieval.
- Configure `EMBED_MODEL=nomic-embed-text-v2-moe`, `OLLAMA_URL=http://localhost:11434`, and optionally `EMBED_INDEX_DIR=data/semantic_index`. Install Ollama, pull the model with `ollama pull nomic-embed-text-v2-moe`, and keep the Ollama service running.
- Current indexed corpus is the scholarship records supplied to the semantic search endpoint. Document-vault RAG and citation-grounded AI answers are separate future integration work; this milestone does not claim those are complete.
- Tests cover persistence/reload, corpus-change rebuild, model-version isolation and empty-corpus handling. Live Nomic/Ollama inference must still be verified on the user's machine because the build environment does not contain the local model service.

## Stage 3 – AI Assistant and guarded tool orchestration

- New authenticated endpoint: `POST /api/assistant/chat` with `{ "message": "...", "conversation_id": null }`.
- Conversation history is stored per authenticated student and can be read through `GET /api/assistant/conversations/{conversation_id}`. The student ID is always taken from the verified session, never from model arguments.
- The coordinator selects a specialist role (`discovery`, `profile_documents`, `eligibility`, `applications`, `tracking`, or `general`), proposes calls only to the six SDD-registered tools, and passes scoped results to a specialist response prompt.
- A hard maximum of five successful tool invocations is enforced per request/task. Unknown tools and unexpected argument keys are rejected.
- The application-preparation tool creates a draft only. There is no submit or approval tool exposed to the model. Final approval remains a separate student action.
- Sensitive income, social-category, date-of-birth, phone, address and identity-number fields are not returned by the profile lookup tool to the LLM. Eligibility remains deterministic in the backend.
- The student frontend chat now calls `/api/assistant/chat` and retains its conversation ID during the active session.

### Stage 3 verification notes

Run tests from the project root with `AUTH_SECRET` configured:

```bash
python -m compileall -q backend tests
pytest -q
```

The current local test run completed with **32 passed** and two FastAPI lifecycle deprecation warnings. These tests verify the tool registry, five-call guard, allow-list, JSON plan parsing and existing project tests. Live Gemini and Ollama tool planning, real external credentials, multi-provider fallback under outages, and full browser-driven UI flows still require testing in the developer's environment. Specialist handoff is currently a controlled coordinator-to-specialist prompt handoff, not independent autonomous agents running concurrently.

## Stage 4 — Document Intelligence

The Document Vault now provides authenticated upload/list/detail/correction/delete endpoints for PDF, JPG and PNG files. Uploads are limited to 20 MB and validated using file signatures (not just browser-provided MIME types). Files are stored under generated names in a local private storage directory; original filenames are metadata only.

### OCR and extraction
- Text PDFs are extracted locally with PyMuPDF.
- Scanned PDF pages and images use Tesseract OCR when installed; PaddleOCR is an optional fallback.
- Extraction method, status, page count, warnings and OCR confidence (when available) are recorded.
- Students can submit corrected field values through `PATCH /api/documents/{document_id}/corrections`.
- `GET /api/documents/consistency/conflicts` flags differing field values across the student's documents for manual review.

### Important safeguards
OCR output is unverified and must be reviewed by the student. Conflicting values are flagged, never automatically reconciled. OCR does not establish authenticity, eligibility or provider acceptance. Document bytes are processed locally; they are not sent to Gemini by this module. Configure `DOCUMENT_STORAGE_DIR` to a private persistent disk in deployment, protect backups, and implement a retention/deletion policy before production use.

### Optional system dependency
Tesseract must be installed separately and available on PATH for OCR. PyMuPDF and Pillow are installed from `requirements.txt`. PaddleOCR is optional and is not installed by default because of its larger runtime footprint.

## Stage 5 — Scholarship discovery, provenance and verification

This stage strengthens the existing crawler and ingestion workflow; it does not auto-publish scraped content.

### Existing live-source monitoring
- Admin-managed HTTPS source watching is available through `/api/admin/sources`.
- Fetching enforces HTTPS, public-address checks, redirect revalidation, robots.txt checks, content-type/size limits and a polite delay.
- Changed pages are extracted and queued as `Pending_Review`; unchanged pages are detected by SHA-256 content hash.
- Extracted fields are validated and possible duplicates are surfaced for administrator review.

### New source registry
- `POST /api/admin/source-registry` registers a candidate source. It remains `Pending_Verification` and is not automatically trusted.
- `GET /api/admin/source-registry` lists source candidates; optional `?status=Pending_Verification` filters them.
- `POST /api/admin/source-registry/{source_id}/review` requires an administrator decision and review notes. A source can become `Verified_Official` only with an evidence URL and explicit human review; rejection is recorded.
- `GET /api/admin/source-registry/{source_id}/history` returns the audit history.
- The registry is an administrative provenance record. It does not independently prove that a website is official, nor does it yet gate the older crawler's `/api/admin/sources` list. Administrators must review and configure watched crawler sources deliberately.

### Ingestion publication safeguards
- Each ingestion record stores source URL, extraction method, extraction timestamp and SHA-256 content hash.
- Ingestion detail and review-history endpoints are available at `GET /api/admin/ingested/{ingest_id}`.
- Publishing requires explicit human verification and review notes; automated checks alone cannot certify a scholarship.
- Required fields and possible duplicates block publication unless the administrator resolves the issue and explicitly allows a duplicate. No automated publishing is performed.
- Review decisions are recorded in `ingestion_audit`.

### Known limitations
- Source discovery is still admin-configured; the system does not discover every scholarship provider on the public internet.
- Website extraction varies by provider layout. JavaScript-only pages, PDFs and authenticated portals may need provider-specific adapters.
- Human verification is required before publication. A verified source record is an administrative assessment, not a guarantee of scholarship authenticity or continued accuracy.
- The DNS check and subsequent HTTP request are separate operations; deploy the crawler in a network-restricted environment and keep the crawler allowlist narrow.

### Stage 5 validation
- `python -m compileall -q backend tests`
- `PYTHONPATH=. pytest -q` — 44 passed, 2 FastAPI lifecycle deprecation warnings.

No additional Python dependency was added for Stage 5. The existing `requirements.txt` remains the install list.

## Stage 6 — Application preparation workspace

Stage 6 adds provider-neutral application form schemas, student-editable field mapping,
server-side field allow-listing, application validation reports, and student-scoped
workspace retrieval. It deliberately prepares drafts only. It does not submit forms to
scholarship providers or automate OTP, CAPTCHA, biometric verification, payments,
bank details, signatures, or mandatory declarations. Provider-specific field schemas
and real portal adapters must be configured and tested separately before use.

New endpoints:
- `GET /api/applications/{id}/form-schema`
- `GET /api/applications/{id}/workspace`
- `PATCH /api/applications/{id}/workspace`
- `POST /api/applications/{id}/validate`

The validation endpoint reports missing required profile fields and required document
categories, and explicitly does not certify document authenticity or permit submission.

## Stage 7 — application tracking, payments and renewals

Stage 7 adds authenticated, student-scoped records for application status updates, separate scholarship payment reports, and renewal schedules.

### Application tracking
- `POST /api/applications/{application_id}/tracking-updates` records a student-reported status, optional note, acknowledgement reference and optional evidence document from the student's own vault.
- `GET /api/applications/{application_id}/tracking-updates` returns that application's report history.
- Student-reported statuses are labelled `Unverified` and do not silently overwrite the provider/application status.

### Payment tracking
- `POST /api/payments` records a payment status separately from the application status. Amounts are non-negative and currency is an ISO-style three-character code (default INR).
- `GET /api/payments` lists only the authenticated student's payment records.
- `POST /api/admin/payments/{payment_id}/review` lets an administrator record a review decision and note. This is an administrative review record, not a direct bank/provider confirmation unless evidence has actually been checked.

### Renewals
- `POST /api/renewals` creates a renewal record for an application and academic year. Duplicate application/year records are rejected.
- `GET /api/renewals` lists the student's renewals; optional `status` filtering is supported.
- `PATCH /api/renewals/{renewal_id}` updates the student's own renewal deadline, status or notes.
- `GET /api/renewals/due?days=30` lists upcoming renewal deadlines in the requested 0–365 day window. It does not send notifications.

### Safeguards and limitations
- Every endpoint checks ownership using the authenticated session. Admin payment review requires the `admin` role.
- Application status, payment status and renewal status are separate records and must not be conflated.
- Student-entered application/payment statuses remain unverified. No official provider API, bank integration, payment verification, or automatic renewal submission is included in this stage; provider-specific integrations and evidence-based verification remain future work.
- The new SQLite tables are created automatically when the application starts. Back up the database before upgrading an existing deployment.

### Stage 7 verification
- Added tests for student-reported status history, separation of payment/application status, renewal creation/update, and cross-student isolation.
- Full backend test suite: **51 passed**, 2 existing FastAPI lifecycle deprecation warnings.
- Python compilation checked for backend and tests.

## Stage 8 — Personalised scholarship alerts

- The backend periodically evaluates the scholarship catalogue against verified students' saved profiles and creates deduplicated, student-scoped alerts for opportunities that are not deterministically marked `not_eligible`.
- Alerts are generated only from records already admitted to the catalogue. The existing source-ingestion workflow still requires administrator verification before publishing newly extracted records.
- Deadline reminders are generated for saved scholarships at 7, 3 and 1 days before closing. Renewal reminders use renewal dates recorded on the student's application and trigger at 30, 7, 3 and 1 days.
- External email, SMS, WhatsApp and push delivery require both explicit channel consent and valid provider configuration. In-app alerts remain available regardless of external provider configuration.
- The scheduler is in-process and intended for one application worker. For multi-worker/production deployment, use a durable external scheduler/queue and persistent delivery retry records.
- `SCHOLARSHIP_ALERT_INTERVAL_MIN` controls the personalised scholarship scan interval (default 10 minutes).
- A student can request an immediate profile-matching scan with `POST /api/notifications/check`.

## Stage 9 — AI provider routing and student-document RAG
- Central provider routing now selects Gemini 3.8 Flash for primary tasks and Gemini 3.1 Flash-Lite for lightweight tasks (unless model IDs are explicitly overridden), with a bounded Gemini request count and local Qwen3 4B via Ollama as fallback. If neither provider is reachable, the API returns a safe unavailable response; it does not pretend AI succeeded.
- Gemini authentication uses the `x-goog-api-key` header. Set `AI_API_KEY`; set `GEMINI_REQUEST_LIMIT` to the maximum Gemini requests per running process. This is a request-count guard, not a token quota or a billing guarantee. Keep paid billing disabled if you require free-tier-only use.
- Added authenticated `GET /api/assistant/provider-status` to report configured model IDs and environment readiness. It does not prove the remote provider or local model is reachable; a real request is needed to verify connectivity.
- Added student-scoped document retrieval for the AI assistant. It retrieves only the authenticated student's extracted vault text, chunks it, and uses local Nomic embeddings/FAISS where Ollama is available, with a transparent lexical fallback. Excerpts carry document IDs and filenames as source references.
- Privacy boundary: if private document excerpts are included, the final answer is forced through local Ollama only. The document excerpts are not sent to Gemini. If Ollama is unavailable, the assistant falls back safely rather than sending the excerpts to the cloud.
- Nomic embedding remains local (`nomic-embed-text-v2-moe`); the index is isolated by student. Do not share the local data directory between untrusted operating-system users. Install Ollama and pull both models: `ollama pull qwen3:4b` and `ollama pull nomic-embed-text-v2-moe`.
- Live provider credentials, model availability, local RAM/latency, and real student-document question answering must be tested on the deployment machine. The build tests mock neither a live Gemini nor a live Ollama service and do not claim those external services were contacted.


## Stage 10 — Official-source ingestion hardening and version history

- Fixed the ingestion content-hash path so manually submitted announcement text is hashed from the actual submitted text (previously the route referenced an undefined variable).
- Added a persistent source-snapshot ledger keyed by source URL and SHA-256 content hash. Re-submitting identical source content returns the existing ingestion record instead of creating a duplicate review item.
- Added monotonically increasing per-source version numbers and an administrator endpoint, `GET /api/admin/ingested/source-versions?source_url=<encoded-https-url>`, to inspect observed versions, hashes, ingestion IDs and timestamps.
- The scheduled crawler now records the same version ledger for changed pages and avoids creating another review item for an already-seen source/hash pair.
- Provenance now includes the source hostname and source version as well as the URL, extraction timestamp, extraction method and content hash.
- Newly extracted items remain `Pending_Review`; this stage does not auto-publish scholarships or automatically certify websites as official. Configure only sources that administrators have reviewed, respect robots.txt and site terms, and use provider-specific adapters for pages that cannot be safely extracted as ordinary HTML/text.
- Personalised alerts continue to use the existing catalogue workflow: newly extracted opportunities become eligible for matching only after the established human-verification publication step.

### Stage 10 verification
- `python -m compileall -q backend tests` — passed.
- `AUTH_SECRET=... PYTHONPATH=. pytest -q` — **56 passed**, 2 FastAPI lifecycle deprecation warnings.
- Live official-site crawling, Gemini/Ollama calls and outbound notification delivery were not exercised in this environment; complete those checks during final manual setup.

## Stage 11 — Guided official portal handoff

Stage 11 adds a provider-neutral, student-controlled handoff workflow for scholarships with a configured HTTPS `application_url`:

- `GET /api/applications/{application_id}/portal-handoff` previews allowed draft fields, required documents and manual checkpoints.
- `POST /api/applications/{application_id}/portal-handoff` creates a student-owned handoff session only when the scholarship has a configured HTTPS application URL.
- `GET /api/portal-handoff/{session_id}` retrieves the student's own session.
- `PATCH /api/portal-handoff/{session_id}/checkpoint` records student-confirmed progress. Notes are restricted to avoid collecting credentials or sensitive step data.

This is **not** a live integration with every scholarship portal. It does not automate login, OTP, CAPTCHA, biometrics, signatures, declarations, payments, or final submission. It never marks an application as provider-submitted or provider-approved. A portal URL must be configured and independently verified by an administrator before use. The student must complete the official portal workflow and separately record any acknowledgement through the existing tracking feature.

## Stage 12 — baseline security and operational hardening
- Added security response headers (nosniff, frame denial, referrer and permissions policies); HSTS is emitted only when HTTPS termination is explicitly configured.
- Added optional process-local API rate limiting (`RATE_LIMIT_ENABLED`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`). This is a development/MVP safeguard, not a replacement for a shared production gateway or WAF.
- Added `/api/ready` to check local database connectivity, auth-secret strength and document-storage writability. It deliberately does not claim external AI, messaging, OCR or scholarship portals are ready.

## Stage 13 — final integration and deployment handover
- Added `DEPLOYMENT_CHECKLIST.md` covering configuration, data storage, security, external providers, functional acceptance and known MVP boundaries.
- Added `scripts/run_smoke_checks.py` to check public health, readiness and frontend routes after startup/deployment.
- Final local regression suite: `AUTH_SECRET='...' PYTHONPATH=. pytest -q` — 63 passed, 2 FastAPI lifecycle deprecation warnings. Python compilation is checked separately. Live provider credentials, production infrastructure, real scholarship source coverage and individual portal adapters still require deployment-time verification.
