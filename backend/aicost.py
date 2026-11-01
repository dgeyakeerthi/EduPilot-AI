"""Persistent AI usage/cost log. Costs are estimates assuming Gemini free tier / local Ollama (paid billing must stay disabled)."""
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import Depends
import os
from backend.ai import router as ai

def setup(app, user, db, err, now):
    def tdb():
        c = db(); c.executescript("CREATE TABLE IF NOT EXISTS ai_calls(id TEXT PRIMARY KEY,at TEXT,provider TEXT,task TEXT,light INT,in_tokens INT,out_tokens INT,est_cost_usd REAL);"); return c
    def hook(r):
        c = tdb(); c.execute("INSERT INTO ai_calls VALUES(?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), now(), r["provider"], r["task"], int(r["light"]), r["prompt_chars"] // 4, r["response_chars"] // 4, 0.0)); c.commit()
    ai.usage_hook = hook

    @app.get("/api/admin/ai-cost")
    def cost(u=Depends(user)):
        if u["role"] != "admin": raise err("forbidden", "Administrator access required", 403)
        c = tdb(); since = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        q = lambda s, *a: [dict(r) for r in c.execute(s, a)]
        today = now()[:10]; used = q("SELECT COALESCE(SUM(in_tokens+out_tokens),0) t FROM ai_calls WHERE provider='gemini' AND at LIKE ?", today + "%")[0]["t"]
        budget = int(os.environ.get("AI_DAILY_TOKEN_BUDGET", "0") or 0)
        return {"by_provider": q("SELECT provider, COUNT(*) calls, SUM(in_tokens) in_tokens, SUM(out_tokens) out_tokens, SUM(est_cost_usd) est_cost_usd FROM ai_calls GROUP BY provider"),
                "by_day_last_14": q("SELECT substr(at,1,10) day, provider, COUNT(*) calls FROM ai_calls WHERE at>=? GROUP BY day, provider ORDER BY day", since),
                "gemini_tokens_today": used, "daily_budget_used_pct": round(100 * used / budget, 1) if budget else None,
                "note": "Token counts are estimates (chars/4). Cost assumes free tier or local models; keep paid billing disabled."}
