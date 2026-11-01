import os, tempfile
os.environ.setdefault("AUTH_SECRET", "stage11-test-secret")
os.environ.setdefault("EDUPILOT_DEMO_MODE", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)

def student(email):
    r=client.post('/api/auth/register',json={'email':email,'password':'password123','full_name':'Portal Student'}).json()
    client.post('/api/auth/verify',json={'email':email,'code':r['demo_verification_code']})
    token=client.post('/api/auth/login',json={'email':email,'password':'password123'}).json()['token']
    return {'Authorization':'Bearer '+token}

def draft(h):
    return client.post('/api/applications/prepare',headers=h,json={'scholarship_id':'11111111-0000-4000-8000-000000000001'}).json()['application_id']

def test_handoff_preview_never_claims_automation_or_submission():
    h=student('stage11a@example.com'); aid=draft(h)
    r=client.get(f'/api/applications/{aid}/portal-handoff',headers=h)
    assert r.status_code==200
    body=r.json()
    assert body['portal_available'] is False
    assert body['automated_actions']==[]
    assert body['manual_checkpoints']
    assert body['safety_note']

def test_unconfigured_portal_cannot_create_handoff():
    h=student('stage11b@example.com'); aid=draft(h)
    r=client.post(f'/api/applications/{aid}/portal-handoff',headers=h)
    assert r.status_code==409 and r.json()['error']['code']=='portal_not_configured'

def test_student_cannot_read_another_students_handoff():
    h=student('stage11c@example.com'); aid=draft(h)
    other=student('stage11d@example.com')
    assert client.get(f'/api/applications/{aid}/portal-handoff',headers=other).status_code==404

def test_configured_https_portal_handoff_and_checkpoint_are_student_reported():
    import backend.main as main
    scholarship = next(x for x in main.SCHOLARSHIPS if x['scholarship_id']=='11111111-0000-4000-8000-000000000001')
    original = scholarship.get('application_url')
    scholarship['application_url'] = 'https://scholarships.example.org/apply'
    try:
        h=student('stage11e@example.com'); aid=draft(h)
        created=client.post(f'/api/applications/{aid}/portal-handoff',headers=h)
        assert created.status_code==201
        sid=created.json()['session_id']
        update=client.patch(f'/api/portal-handoff/{sid}/checkpoint',headers=h,json={'checkpoint_index':0,'completed':True,'note':'Opened portal'})
        assert update.status_code==200
        assert update.json()['provider_submission_confirmed'] is False
        assert update.json()['checkpoints'][0]['completed'] is True
        assert client.patch(f'/api/portal-handoff/{sid}/checkpoint',headers=h,json={'checkpoint_index':1,'completed':True,'note':'My OTP is 123456'}).status_code==422
    finally:
        scholarship['application_url'] = original
