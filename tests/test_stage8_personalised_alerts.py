import os, sys
from pathlib import Path
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('AUTH_SECRET','stage8-test-secret-change-me')
os.environ.setdefault('EDUPILOT_DEMO_MODE','true')
from backend.main import app
client=TestClient(app)

def login(email):
    r=client.post('/api/auth/register',json={'email':email,'password':'StrongPass123','full_name':'Alert Student'})
    assert r.status_code==201, r.text
    code=r.json()['demo_verification_code']
    assert client.post('/api/auth/verify',json={'email':email,'code':code}).status_code==200
    r=client.post('/api/auth/login',json={'email':email,'password':'StrongPass123'})
    return {'Authorization':'Bearer '+r.json()['token']}

def test_personalised_alerts_are_created_and_deduplicated():
    h=login('stage8-alert@example.com')
    client.put('/api/students/me',headers=h,json={'education_level':'Undergraduate','course_name':'B.Tech','state':'Andhra Pradesh','preferred_language':'English'})
    first=client.post('/api/notifications/check',headers=h)
    assert first.status_code==200, first.text
    second=client.post('/api/notifications/check',headers=h)
    assert second.status_code==200, second.text
    notes=client.get('/api/notifications',headers=h).json()
    ids=[n.get('scholarship_id') for n in notes if n.get('kind')=='new_scholarship']
    assert len(ids)==len(set(ids))

def test_student_cannot_view_another_students_alerts():
    h1=login('stage8-owner@example.com'); h2=login('stage8-other@example.com')
    client.put('/api/students/me',headers=h1,json={'education_level':'Undergraduate','course_name':'B.Tech'})
    client.post('/api/notifications/check',headers=h1)
    own=client.get('/api/notifications',headers=h1).json()
    other=client.get('/api/notifications',headers=h2).json()
    assert len(other)==0
