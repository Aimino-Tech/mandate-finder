from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.security import hash_api_key
from src.db.models import APIKey, CRMConnection, CRMSyncLog
from src.services.crm_service import CRMType, SyncResult, decrypt_token, encrypt_token

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def _seed_key(test_session_factory: async_sessionmaker):
    async with test_session_factory() as s:
        s.add(APIKey(key_hash=hash_api_key("test-mf-key-123"), name="T", scopes=["*"], tier="agency"))
        await s.commit()


@pytest.fixture
def auth_hdrs(_seed_key):
    return {"Authorization": "Bearer test-mf-key-123"}


def test_sync_result():
    assert SyncResult(success=True, contact_id="c1").to_dict()["success"]


def test_crm_enum():
    assert CRMType.HUBSPOT.value == "hubspot"


def test_encrypt_roundtrip():
    t = "secret"
    assert decrypt_token(encrypt_token(t)) == t


def test_encrypt_empty():
    assert encrypt_token("") == "" and decrypt_token("") == ""


async def test_config(client: AsyncClient):
    r = await client.get("/api/v1/crm/config")
    assert r.status_code == 200
    assert {i["crm_type"] for i in r.json()} == {"hubspot", "pipedrive", "salesforce"}


async def test_list_empty(client: AsyncClient, auth_hdrs):
    r = await client.get("/api/v1/crm/connections", headers=auth_hdrs)
    assert r.status_code == 200 and r.json() == []


async def test_connect_pd(client: AsyncClient, auth_hdrs, test_session_factory):
    r = await client.post("/api/v1/crm/connect", headers=auth_hdrs,
                          json={"crm_type": "pipedrive", "api_token": "tok"})
    assert r.status_code == 201 and r.json()["crm_type"] == "pipedrive"
    async with test_session_factory() as s:
        c = (await s.execute(select(CRMConnection))).scalar_one()
        assert decrypt_token(c.encrypted_access_token) == "tok"


async def test_dup(client: AsyncClient, auth_hdrs):
    await client.post("/api/v1/crm/connect", headers=auth_hdrs,
                      json={"crm_type": "pipedrive", "api_token": "a"})
    r = await client.post("/api/v1/crm/connect", headers=auth_hdrs,
                          json={"crm_type": "pipedrive", "api_token": "b"})
    assert r.status_code == 409


async def test_no_token(client: AsyncClient, auth_hdrs):
    r = await client.post("/api/v1/crm/connect", headers=auth_hdrs,
                          json={"crm_type": "pipedrive"})
    assert r.status_code == 400


async def test_disconnect(client: AsyncClient, auth_hdrs, test_session_factory):
    await client.post("/api/v1/crm/connect", headers=auth_hdrs,
                      json={"crm_type": "pipedrive", "api_token": "t"})
    async with test_session_factory() as s:
        cid = (await s.execute(select(CRMConnection))).scalar_one().id
        r = await client.delete(f"/api/v1/crm/connections/{cid}", headers=auth_hdrs)
        assert r.status_code == 204


async def test_fm(client: AsyncClient, auth_hdrs, test_session_factory):
    await client.post("/api/v1/crm/connect", headers=auth_hdrs,
                      json={"crm_type": "pipedrive", "api_token": "t"})
    async with test_session_factory() as s:
        cid = (await s.execute(select(CRMConnection))).scalar_one().id
        r = await client.put(f"/api/v1/crm/connections/{cid}/field-mapping",
                             headers=auth_hdrs, json={"field_mapping": {"e": "E"}})
        assert r.status_code == 200


async def test_as(client: AsyncClient, auth_hdrs, test_session_factory):
    await client.post("/api/v1/crm/connect", headers=auth_hdrs,
                      json={"crm_type": "pipedrive", "api_token": "t"})
    async with test_session_factory() as s:
        cid = (await s.execute(select(CRMConnection))).scalar_one().id
        r = await client.put(f"/api/v1/crm/connections/{cid}/auto-sync",
                             headers=auth_hdrs, json={"enabled": True})
        assert r.json()["auto_sync_enabled"]


async def test_sync_404(client: AsyncClient, auth_hdrs):
    r = await client.post("/api/v1/crm/sync", headers=auth_hdrs, json={"lead_ids": ["x"]})
    assert r.status_code == 404


async def test_sync_200(client: AsyncClient, auth_hdrs):
    await client.post("/api/v1/crm/connect", headers=auth_hdrs,
                      json={"crm_type": "pipedrive", "api_token": "t"})
    r = await client.post("/api/v1/crm/sync", headers=auth_hdrs, json={"lead_ids": ["a", "b"]})
    assert r.status_code == 200 and len(r.json()["results"]) == 2


async def test_hist_empty(client: AsyncClient, auth_hdrs):
    r = await client.get("/api/v1/crm/sync-history", headers=auth_hdrs)
    assert r.json()["total"] == 0


async def test_webhook_400(client: AsyncClient):
    r = await client.post("/api/v1/crm/webhook/lead-matched", json={})
    assert r.status_code == 400


async def test_retry(client: AsyncClient, auth_hdrs, test_session_factory):
    await client.post("/api/v1/crm/connect", headers=auth_hdrs,
                      json={"crm_type": "pipedrive", "api_token": "t"})
    async with test_session_factory() as s:
        c = (await s.execute(select(CRMConnection))).scalar_one()
        c.synced_lead_ids = ["f1", "f2"]
        await s.commit()
    r = await client.post("/api/v1/crm/sync/retry", headers=auth_hdrs)
    assert r.status_code == 200 and len(r.json()["results"]) == 2


async def test_logs_created(client: AsyncClient, auth_hdrs, test_session_factory):
    await client.post("/api/v1/crm/connect", headers=auth_hdrs,
                      json={"crm_type": "pipedrive", "api_token": "t"})
    await client.post("/api/v1/crm/sync", headers=auth_hdrs, json={"lead_ids": ["lg"]})
    async with test_session_factory() as s:
        assert (await s.execute(select(CRMSyncLog))).scalars().all()
