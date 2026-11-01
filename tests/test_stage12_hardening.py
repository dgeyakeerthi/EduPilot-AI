import os, tempfile
os.environ.setdefault("AUTH_SECRET", "stage12-test-secret-with-more-than-32-chars")
os.environ.setdefault("EDUPILOT_DEMO_MODE", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from backend.main import app
client=TestClient(app)

def test_readiness_reports_core_local_dependencies_only():
    r=client.get('/api/ready')
    assert r.status_code==200
    assert r.json()['status'] in {'ready', 'degraded'}
    assert r.json()['checks']['database'] == 'ok'
    assert 'external AI' in r.json()['note']

def test_security_headers_present():
    r=client.get('/api/health')
    assert r.headers['x-content-type-options']=='nosniff'
    assert r.headers['x-frame-options']=='DENY'
    assert r.headers['referrer-policy']=='strict-origin-when-cross-origin'
