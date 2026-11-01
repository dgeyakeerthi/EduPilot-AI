import pytest
from backend.source_registry import _public_https
from backend.ingest import clean, tokens, jaccard

def test_source_registry_requires_https():
    with pytest.raises(ValueError):
        _public_https("http://example.com/scholarships")

def test_source_registry_rejects_credentials_in_url():
    with pytest.raises(ValueError):
        _public_https("https://user:pass@example.com/path")

def test_source_registry_rejects_localhost_before_dns():
    with pytest.raises(ValueError):
        _public_https("https://localhost/scholarships")

def test_ingestion_cleaning_does_not_invent_required_fields():
    record = clean({"scholarship_name": "Example", "closing_date": "not-a-date", "criteria": [{"field":"unknown","op":"eq","value":1}]})
    assert record["closing_date"] is None
    assert record["criteria"] is None
    assert record.get("provider_name") is None

def test_duplicate_similarity_is_deterministic():
    a=tokens({"scholarship_name":"National Merit Scholarship","provider_name":"Education Department"})
    b=tokens({"scholarship_name":"National Merit Scholarship","provider_name":"Education Department"})
    assert jaccard(a,b) == 1.0


def test_ingestion_source_snapshot_hash_and_idempotency(monkeypatch):
    """Regression: ingestion hashes the submitted text and records repeat snapshots once."""
    import os
    from fastapi.testclient import TestClient
    from backend.main import app
    import backend.ingest as ingestion

    os.environ["ADMIN_EMAILS"] = "stage10-admin@example.com"
    client = TestClient(app)
    reg = client.post("/api/auth/register", json={"email":"stage10-admin@example.com", "password":"StrongPass123", "full_name":"Admin"})
    assert reg.status_code == 201, reg.text
    code = reg.json().get("demo_verification_code")
    assert code
    assert client.post("/api/auth/verify", json={"email":"stage10-admin@example.com", "code":code}).status_code == 200
    token = client.post("/api/auth/login", json={"email":"stage10-admin@example.com", "password":"StrongPass123"}).json()["token"]
    headers = {"Authorization":"Bearer " + token}
    monkeypatch.setattr(ingestion, "extract", lambda text: ({"scholarship_name":"Stage Ten Grant", "provider_name":"Test Foundation", "closing_date":"2027-01-31", "eligible_education_levels":["Undergraduate"], "criteria":[{"field":"state","op":"eq","value":"Andhra Pradesh"}]}, "test"))
    payload = {"source_url":"https://example.org/grants", "raw_text":"A sufficiently long official scholarship announcement text for testing."}
    first = client.post("/api/admin/sources/ingest", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["provenance"]["content_sha256"]
    second = client.post("/api/admin/sources/ingest", headers=headers, json=payload)
    assert second.status_code == 201, second.text
    assert second.json()["duplicate_snapshot"] is True
    assert second.json()["ingest_id"] == first.json()["ingest_id"]
