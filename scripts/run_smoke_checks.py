"""Post-deployment HTTP smoke test. Usage: python scripts/smoke_test.py https://your-host"""
import sys, urllib.request, urllib.error

base=(sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8000").rstrip("/")
checks=[("health", "/api/health", {200}), ("readiness", "/api/ready", {200}), ("student app", "/", {200})]
failed=[]
for name, path, expected in checks:
    try:
        req=urllib.request.Request(base+path, headers={"User-Agent":"EduPilot-SmokeTest/1.0"})
        with urllib.request.urlopen(req, timeout=10) as res:
            body=res.read(5000).decode("utf-8", "replace")
            ok=res.status in expected
            if name=="readiness" and '"status":"degraded"' in body: ok=False
            print(f"{'PASS' if ok else 'FAIL'} {name}: HTTP {res.status}")
            if not ok: failed.append(name)
    except Exception as exc:
        print(f"FAIL {name}: {type(exc).__name__}: {exc}"); failed.append(name)
if failed:
    print("Smoke test failed:", ", ".join(failed)); sys.exit(1)
print("All public endpoint smoke checks passed. Authenticated workflows still need manual verification.")
