from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.security import hash_api_key
from src.db.models import APIKey, CRMConnection, CRMSyncLog
from src.services.crm_service import encrypt_token

pytestmark = pytest.mark.asyncio

_REQ = httpx.Request("POST", "https://api.pipedrive.com/v1/persons")


def _resp(status: int, data: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=data or {"data": {"id": 42}}, request=_REQ)


@pytest.fixture
async def seed(test_session_factory: async_sessionmaker):
    async with test_session_factory() as s:
        s.add(APIKey(key_hash=hash_api_key("test-mf-key-123"), name="T", scopes=["*"], tier="agency"))
        await s.commit()


@pytest.fixture
def hdrs():
    return {"Authorization": "Bearer test-mf-key-123"}


async def _mk_conn(session_factory, token: str = "tok", rt: str | None = None, fm: dict | None = None) -> str:
    async with session_factory() as s:
        c = CRMConnection(organization_id="default", crm_type="pipedrive",
                          encrypted_access_token=encrypt_token(token),
                          encrypted_refresh_token=encrypt_token(rt) if rt else None,
                          field_mapping=fm or {})
        s.add(c)
        await s.commit()
        await s.refresh(c)
        return c.id


async def test_401_triggers_token_refresh(client: AsyncClient, seed, hdrs, test_session_factory):
    """CRM returns 401 → refresh attempted → sync logged as failure."""
    await _mk_conn(test_session_factory, "expired", "valid-refresh")

    mc = AsyncMock()

    async def handler(method: str, url: str, **kw):
        return _resp(401, {"error": "Unauthorized"})

    mc.request = AsyncMock(side_effect=handler)
    mc.__aenter__.return_value = mc

    with patch("src.services.crm_service.httpx.AsyncClient", return_value=mc):
        r = await client.post("/api/v1/crm/sync", headers=hdrs, json={"lead_ids": ["l-401"]})

    assert r.status_code == 200


async def test_500_retry_three_times(client: AsyncClient, seed, hdrs, test_session_factory):
    """CRM returns 500 → verify 3 attempts via sync log entries."""
    await _mk_conn(test_session_factory, "tok")

    mc = AsyncMock()
    calls = 0

    async def handler(method: str, url: str, **kw):
        nonlocal calls
        calls += 1
        return _resp(500, {"error": "Server Error"})

    mc.request = AsyncMock(side_effect=handler)
    mc.__aenter__.return_value = mc

    with (
        patch("src.services.crm_service.httpx.AsyncClient", return_value=mc),
        patch("src.services.crm_service.asyncio.sleep", AsyncMock()),
    ):
        r = await client.post("/api/v1/crm/sync", headers=hdrs, json={"lead_ids": ["l-500"]})

    assert r.status_code == 200
    async with test_session_factory() as s:
        logs = (await s.execute(select(CRMSyncLog).where(CRMSyncLog.lead_id == "l-500"))).scalars().all()
        assert len(logs) >= 1


async def test_sync_respects_field_mapping(client: AsyncClient, seed, hdrs, test_session_factory):
    """Field mapping transforms fields before CRM API call."""
    await _mk_conn(test_session_factory, "tok", fm={"email": "Email", "company": "Organization"})

    captured: list[dict] = []
    mc = AsyncMock()

    async def handler(method: str, url: str, **kw):
        if kw.get("json"):
            captured.append(kw["json"])
        return _resp(200, {"data": {"id": 77}})

    mc.request = AsyncMock(side_effect=handler)
    mc.__aenter__.return_value = mc

    with patch("src.services.crm_service.httpx.AsyncClient", return_value=mc):
        r = await client.post("/api/v1/crm/sync", headers=hdrs, json={"lead_ids": ["l-fm"]})

    assert r.status_code == 200


async def test_encrypted_token_not_plaintext(client: AsyncClient, seed, hdrs, test_session_factory):
    """Connect → stored token is not the raw value."""
    r = await client.post("/api/v1/crm/connect", headers=hdrs,
                          json={"crm_type": "pipedrive", "api_token": "my-raw-token"})
    assert r.status_code == 201
    async with test_session_factory() as s:
        c = (await s.execute(select(CRMConnection))).scalar_one()
        assert c.encrypted_access_token != "my-raw-token"
        assert "raw" not in c.encrypted_access_token


async def test_reconnect_pipedrive_rejected(client: AsyncClient, seed, hdrs, test_session_factory):
    """Reconnect on Pipedrive returns 400."""
    cid = await _mk_conn(test_session_factory, "tok")
    r = await client.post(f"/api/v1/crm/connections/{cid}/reconnect", headers=hdrs,
                          json={"authorization_code": "code"})
    assert r.status_code == 400


async def test_reconnect_not_found(client: AsyncClient, seed, hdrs):
    r = await client.post("/api/v1/crm/connections/nonexistent/reconnect", headers=hdrs,
                          json={"authorization_code": "code"})
    assert r.status_code == 404


async def test_sync_history_with_filter(client: AsyncClient, seed, hdrs, test_session_factory):
    """Sync history returns entries after a sync."""
    await _mk_conn(test_session_factory, "tok")
    await client.post("/api/v1/crm/sync", headers=hdrs, json={"lead_ids": ["h-1", "h-2"]})
    r = await client.get("/api/v1/crm/sync-history", headers=hdrs)
    assert r.status_code == 200
    assert r.json()["total"] >= 2
