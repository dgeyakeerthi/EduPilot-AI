"""Stage 12: baseline HTTP hardening and operational readiness checks.

This is defense-in-depth for the MVP, not a substitute for a production gateway,
managed secrets, TLS termination, persistent rate limiting or security review.
"""
from __future__ import annotations
import os, sqlite3, time
from collections import defaultdict, deque
from pathlib import Path
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        # HSTS is added only when deployment explicitly confirms HTTPS termination.
        if os.getenv("EDUPILOT_HTTPS_TERMINATED", "false").lower() == "true":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

class OptionalRateLimitMiddleware(BaseHTTPMiddleware):
    """Small single-process guard; set RATE_LIMIT_ENABLED=true. Use a shared gateway in production."""
    def __init__(self, app, limit=120, window=60):
        super().__init__(app); self.limit=max(1, int(limit)); self.window=max(1, int(window)); self.hits=defaultdict(deque)
    async def dispatch(self, request: Request, call_next):
        if os.getenv("RATE_LIMIT_ENABLED", "false").lower() != "true" or not request.url.path.startswith("/api/"):
            return await call_next(request)
        host = request.client.host if request.client else "unknown"
        now = time.monotonic(); q=self.hits[host]
        while q and now-q[0] > self.window: q.popleft()
        if len(q) >= self.limit:
            from starlette.responses import JSONResponse
            return JSONResponse({"error":{"code":"rate_limited","message":"Too many requests. Try again shortly.","details":{}},"request_id":"rate-limit"}, status_code=429, headers={"Retry-After":str(self.window)})
        q.append(now)
        return await call_next(request)

def setup(app, db_path):
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(OptionalRateLimitMiddleware,
        limit=int(os.getenv("RATE_LIMIT_REQUESTS", "120")),
        window=int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))

    @app.get("/api/ready")
    def ready():
        checks={"database":"ok", "auth_secret":"configured", "document_storage":"ok"}
        try:
            conn=sqlite3.connect(db_path, timeout=3); conn.execute("SELECT 1"); conn.close()
        except Exception:
            checks["database"]="unavailable"
        if not os.getenv("AUTH_SECRET") or len(os.getenv("AUTH_SECRET", "")) < 32:
            checks["auth_secret"]="weak_or_missing"
        storage=Path(os.getenv("DOCUMENT_STORAGE_DIR", "data/documents"))
        try:
            storage.mkdir(parents=True, exist_ok=True)
            probe=storage / ".edupilot_write_check"; probe.write_text("ok", encoding="utf-8"); probe.unlink()
        except Exception:
            checks["document_storage"]="unwritable"
        ok=all(v in ("ok", "configured") for v in checks.values())
        return {"status":"ready" if ok else "degraded", "checks":checks,
                "note":"Readiness does not verify external AI, email, SMS, OCR or scholarship portal providers."}
