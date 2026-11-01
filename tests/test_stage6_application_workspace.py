import os, tempfile
os.environ.setdefault("AUTH_SECRET", "stage6-test-secret")
os.environ.setdefault("EDUPILOT_DEMO_MODE", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)

def student(email):
    r=client.post('/api/auth/register',json={'email':email,'password':'password123','full_name':'Stage Six Student'}).json()
    client.post('/api/auth/verify',json={'email':email,'code':r['demo_verification_code']})
    return {'Authorization':'Bearer '+client.post('/api/auth/login',json={'email':email,'password':'password123'}).json()['token']}

def create_draft(h):
    return client.post('/api/applications/prepare',headers=h,json={'scholarship_id':'11111111-0000-4000-8000-000000000001'}).json()['application_id']

def test_workspace_schema_and_student_scoped_read():
    h=student('stage6a@example.com'); aid=create_draft(h)
    r=client.get(f'/api/applications/{aid}/form-schema',headers=h)
    assert r.status_code==200 and any(x['key']=='full_name' for x in r.json()['fields'])
    other=student('stage6b@example.com')
    assert client.get(f'/api/applications/{aid}/workspace',headers=other).status_code==404

def test_workspace_update_and_validation_reports_missing_documents():
    h=student('stage6c@example.com'); aid=create_draft(h)
    r=client.patch(f'/api/applications/{aid}/workspace',headers=h,json={'form_fields':{'full_name':'Student Name','institution_name':'IIIT Lucknow','education_level':'Undergraduate','state':'Uttar Pradesh'}})
    assert r.status_code==200 and r.json()['application_status']=='Draft'
    v=client.post(f'/api/applications/{aid}/validate',headers=h).json()
    assert not v['valid_for_student_review'] and v['missing_documents']
    assert v['submission_allowed'] is False

def test_unknown_fields_rejected_and_approval_reset_on_edit():
    h=student('stage6d@example.com'); aid=create_draft(h)
    bad=client.patch(f'/api/applications/{aid}/workspace',headers=h,json={'form_fields':{'bank_account':'123'}})
    assert bad.status_code==422
    assert client.post(f'/api/applications/{aid}/approval',headers=h,json={'decision':'approve'}).status_code==409
