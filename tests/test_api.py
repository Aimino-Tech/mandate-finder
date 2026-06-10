from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from market_intelligence.main import app
from market_intelligence.models import JobPosting, EarlySignal

client = TestClient(app)


def test_ingest():
    r = client.post("/api/market-intelligence/postings", json=[JobPosting(id="p1", title="E", company="T", posted_at=datetime.now().isoformat()).model_dump(mode="json")])
    assert r.status_code == 200 and r.json()["ingested"] == 1


def test_ingest_signals():
    r = client.post("/api/market-intelligence/signals", json=[EarlySignal(signal_type="funding", company="T", headline="T raise", source_url="https://x.com", detected_at=datetime.now().isoformat(), confidence=0.8).model_dump(mode="json")])
    assert r.status_code == 200 and r.json()["ingested"] == 1


def test_top_roles():
    for i in range(5):
        client.post("/api/market-intelligence/postings", json=[JobPosting(id=str(i), title="E", company="T", role_category="engineering", posted_at=(datetime.now() - timedelta(days=i)).isoformat()).model_dump(mode="json")])
    assert client.get("/api/market-intelligence/top-roles?days=90&limit=5").status_code == 200


def test_industry_pulse():
    assert client.get("/api/market-intelligence/industry-pulse?days=90").status_code == 200


def test_warnings():
    assert client.get("/api/market-intelligence/early-warnings?min_confidence=0.5").status_code == 200


def test_export():
    r = client.get("/api/market-intelligence/trends/export")
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]


def test_trends():
    assert client.get("/api/market-intelligence/trends").status_code == 200


def test_health():
    r = client.get("/api/market-intelligence/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_dashboard():
    r = client.get("/")
    assert r.status_code == 200 and "Market Intelligence Dashboard" in r.text
