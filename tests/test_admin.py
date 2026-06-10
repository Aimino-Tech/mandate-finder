
import pytest
from httpx import AsyncClient

from src.core.security import generate_api_key
from src.db.models import APIKey, MetricEvent


@pytest.fixture
async def agency_api_key(test_session_factory):
    async with test_session_factory() as session:
        raw, key_hash = generate_api_key()
        api_key = APIKey(key_hash=key_hash, name="Admin Test Key", tier="agency")
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)
    return raw


@pytest.fixture
async def auth_headers(agency_api_key):
    return {"Authorization": f"Bearer {agency_api_key}"}


@pytest.fixture
async def solo_api_key(test_session_factory):
    async with test_session_factory() as session:
        raw, key_hash = generate_api_key()
        api_key = APIKey(key_hash=key_hash, name="Solo Test Key", tier="solo")
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)
    return raw


@pytest.mark.asyncio
async def test_non_admin_gets_403(client: AsyncClient, solo_api_key: str):
    headers = {"Authorization": f"Bearer {solo_api_key}"}
    response = await client.get("/api/v1/admin/dashboard", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_dashboard(client: AsyncClient, auth_headers: dict, test_session_factory):
    async with test_session_factory() as session:
        for i in range(5):
            session.add_all([
                MetricEvent(metric_type="mrr", value=10000.0 + i * 1000),
                MetricEvent(metric_type="active_users", value=float(50 + i * 5)),
                MetricEvent(metric_type="churn_rate", value=0.05 - i * 0.01),
            ])
        await session.commit()

    response = await client.get("/api/v1/admin/dashboard?days=30", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "mrr" in data
    assert "active_users" in data
    assert "churn_rate" in data


@pytest.mark.asyncio
async def test_admin_pipeline(client: AsyncClient, auth_headers: dict, test_session_factory):
    async with test_session_factory() as session:
        for mt in ("jobs_ingested", "jobs_enriched", "jobs_scored"):
            for i in range(3):
                session.add(MetricEvent(metric_type=mt, value=100.0 * (i + 1), source="test_source"))
        await session.commit()

    response = await client.get("/api/v1/admin/pipeline?days=30", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "ingested" in data
    assert "enriched" in data
    assert "scored" in data


@pytest.mark.asyncio
async def test_admin_pipeline_sources(client: AsyncClient, auth_headers: dict, test_session_factory):
    async with test_session_factory() as session:
        for source in ("source_a", "source_b"):
            for i in range(3):
                session.add(MetricEvent(metric_type="jobs_ingested", value=100.0 * (i + 1), source=source))
        await session.commit()

    response = await client.get("/api/v1/admin/pipeline/sources?days=30", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "sources" in data
    assert "totals" in data


@pytest.mark.asyncio
async def test_admin_health(client: AsyncClient, auth_headers: dict, test_session_factory):
    async with test_session_factory() as session:
        for mt in ("worker_queue_depth", "api_latency_p95", "error_rate"):
            session.add(MetricEvent(metric_type=mt, value=0.5))
        await session.commit()

    response = await client.get("/api/v1/admin/health?days=7", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "worker_queue_depth" in data
    assert "api_latency_p95" in data
    assert "error_rate" in data

    now = await client.get("/api/v1/admin/health/current", headers=auth_headers)
    assert now.status_code == 200
    for key in ("worker_queue_depth", "api_latency_p95", "error_rate"):
        assert key in now.json()


@pytest.mark.asyncio
async def test_admin_record_metric(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/admin/metrics",
        headers=auth_headers,
        json={"metric_type": "mrr", "value": 15000.0, "source": "test", "labels": {"env": "test"}},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_admin_api_keys(client: AsyncClient, auth_headers: dict, test_session_factory):
    async with test_session_factory() as session:
        for i in range(3):
            raw, key_hash = generate_api_key()
            session.add(APIKey(key_hash=key_hash, name=f"Key {i}", tier="solo"))
        await session.commit()

    response = await client.get("/api/v1/admin/api-keys", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "api_keys" in data
    assert data["total"] >= 3


@pytest.mark.asyncio
async def test_admin_export_csv(client: AsyncClient, auth_headers: dict, test_session_factory):
    async with test_session_factory() as session:
        for i in range(5):
            session.add(MetricEvent(metric_type="mrr", value=float(1000 * (i + 1)), source="csv_test"))
        await session.commit()

    response = await client.get("/api/v1/admin/export?metric_type=mrr&days=30", headers=auth_headers)
    assert response.status_code == 200
    lines = [line.rstrip("\r") for line in response.text.strip().split("\n")]
    assert len(lines) >= 2
    assert lines[0] == "date,metric_type,value,source"


@pytest.mark.asyncio
async def test_admin_alerts_crud(client: AsyncClient, auth_headers: dict):  # noqa: ARG001
    response = await client.post(
        "/api/v1/admin/alerts",
        headers=auth_headers,
        json={"metric_type": "error_rate", "condition": "gt", "threshold": 0.1, "window_minutes": 15},
    )
    assert response.status_code == 201
    alert_id = response.json()["id"]

    response = await client.get("/api/v1/admin/alerts", headers=auth_headers)
    assert response.status_code == 200
    assert any(a["id"] == alert_id for a in response.json())

    response = await client.put(
        f"/api/v1/admin/alerts/{alert_id}",
        headers=auth_headers,
        json={"threshold": 0.2, "enabled": False},
    )
    assert response.status_code == 200
    assert response.json()["threshold"] == 0.2
    assert response.json()["enabled"] is False

    response = await client.delete(f"/api/v1/admin/alerts/{alert_id}", headers=auth_headers)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_admin_alert_invalid_condition(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/admin/alerts",
        headers=auth_headers,
        json={"metric_type": "error_rate", "condition": "invalid", "threshold": 0.1},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_no_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/dashboard")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_export_no_data(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/admin/export?metric_type=nonexistent&days=1", headers=auth_headers)
    assert response.status_code == 200
    lines = [line.rstrip("\r") for line in response.text.strip().split("\n")]
    assert len(lines) >= 1
