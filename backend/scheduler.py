"""Tiny in-process scheduler (single process only; use one uvicorn worker or an external cron for multi-worker setups)."""
import os, threading, time
from datetime import datetime, timezone
TASKS, status = [], {}
def register(name, interval_s, fn):
    TASKS.append([name, interval_s, fn, time.time()]); status[name] = {"interval_s": interval_s, "last_run": None, "last_result": None}  # first run after one interval
def _loop():
    while True:
        t = time.time()
        for task in TASKS:
            if t - task[3] >= task[1]:
                task[3] = t
                try: res = str(task[2]())[:200]
                except Exception as e: res = f"error: {type(e).__name__}"
                status[task[0]].update(last_run=datetime.now(timezone.utc).isoformat(), last_result=res)
        time.sleep(30)
def start():
    if os.environ.get("SCHEDULER_ENABLED", "true").lower() != "true" or getattr(start, "on", False): return
    start.on = True; threading.Thread(target=_loop, daemon=True).start()
