import os, sys, uuid
from pathlib import Path
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault("AUTH_SECRET","stage7-test-secret-change-me")
os.environ.setdefault("EDUPILOT_DEMO_MODE","true")
from backend.main import app, db

client=TestClient(app)

def register_login(email):
    r=client.post('/api/auth/register',json={'email':email,'password':'StrongPass123','full_name':'Test Student'})
    assert r.status_code==201, r.text
    code=r.json()['demo_verification_code']
    assert client.post('/api/auth/verify',json={'email':email,'code':code}).status_code==200
    r=client.post('/api/auth/login',json={'email':email,'password':'StrongPass123'})
    assert r.status_code==200, r.text
    return {'Authorization':'Bearer '+r.json()['token']}

def application(headers):
    scholarships=client.get('/api/demo/scholarships').json()
    open_s=next(x for x in scholarships if x.get('scholarship_status')=='Open')
    r=client.post('/api/applications/prepare',headers=headers,json={'scholarship_id':open_s['scholarship_id']})
    assert r.status_code==201, r.text
    return r.json()['application_id']

def test_student_can_report_status_but_remains_unverified():
    h=register_login('stage7-status@example.com'); aid=application(h)
    r=client.post(f'/api/applications/{aid}/tracking-updates',headers=h,json={'status':'Under_Review','note':'Portal shows under review'})
    assert r.status_code==201, r.text
    assert r.json()['verification_status']=='Unverified'
    assert client.get(f'/api/applications/{aid}/tracking-updates',headers=h).json()[0]['status']=='Under_Review'

def test_payment_is_separate_from_application_status():
    h=register_login('stage7-payment@example.com'); aid=application(h)
    r=client.post('/api/payments',headers=h,json={'application_id':aid,'amount':5000,'currency':'INR','reported_status':'Paid','transaction_reference':'TX-123'})
    assert r.status_code==201, r.text
    assert r.json()['verified_status']=='Unverified'
    assert len(client.get('/api/payments',headers=h).json())==1
    assert client.get(f'/api/applications/{aid}/status',headers=h).json()['application_status']=='Draft'

def test_renewal_create_update_and_due_listing():
    h=register_login('stage7-renewal@example.com'); aid=application(h)
    r=client.post('/api/renewals',headers=h,json={'application_id':aid,'academic_year':'2027-2028','deadline':'2027-06-30'})
    assert r.status_code==201, r.text
    rid=r.json()['id']
    assert client.patch(f'/api/renewals/{rid}',headers=h,json={'status':'In_Progress'}).status_code==200
    assert client.get('/api/renewals',headers=h).json()[0]['status']=='In_Progress'

def test_user_cannot_read_another_students_renewal():
    h1=register_login('stage7-owner@example.com'); aid=application(h1)
    r=client.post('/api/renewals',headers=h1,json={'application_id':aid,'academic_year':'2028-2029'})
    rid=r.json()['id']
    h2=register_login('stage7-other@example.com')
    assert client.patch(f'/api/renewals/{rid}',headers=h2,json={'status':'Renewed'}).status_code==404
