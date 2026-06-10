import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.security import hash_api_key
from src.db.models import APIKey


@pytest.fixture
async def seed_api_key(test_session_factory: async_sessionmaker):
    key_hash = hash_api_key("test-mf-key-123")
    async with test_session_factory() as session:
        key = APIKey(key_hash=key_hash, name="Test Key", scopes=["*"], tier="professional")
        session.add(key)
        await session.commit()


@pytest.fixture
async def auth_headers():
    return {"Authorization": "Bearer test-mf-key-123"}


class TestAPIKeys:
    async def test_create_api_key(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/api-keys", json={"name": "My Integration", "tier": "solo", "scopes": ["leads:read"]}, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Integration"
        assert data["key"].startswith("mf_")
        assert data["tier"] == "solo"
        assert data["is_active"] is True

    async def test_create_api_key_missing_name(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/api-keys", json={"name": "  ", "tier": "solo"}, headers=auth_headers)
        assert resp.status_code == 400

    async def test_create_api_key_invalid_tier(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/api-keys", json={"name": "Bad Tier", "tier": "enterprise"}, headers=auth_headers)
        assert resp.status_code == 400

    async def test_list_api_keys(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.get("/api/v1/api-keys", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 1

    async def test_get_api_key(self, client: AsyncClient, seed_api_key, auth_headers):
        list_resp = await client.get("/api/v1/api-keys", headers=auth_headers)
        key_id = list_resp.json()["items"][0]["id"]
        resp = await client.get(f"/api/v1/api-keys/{key_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == key_id

    async def test_get_api_key_not_found(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.get("/api/v1/api-keys/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404

    async def test_update_api_key(self, client: AsyncClient, seed_api_key, auth_headers):
        list_resp = await client.get("/api/v1/api-keys", headers=auth_headers)
        key_id = list_resp.json()["items"][0]["id"]
        resp = await client.patch(f"/api/v1/api-keys/{key_id}", json={"name": "Updated Key"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Key"

    async def test_delete_api_key(self, client: AsyncClient, seed_api_key, auth_headers):
        list_resp = await client.get("/api/v1/api-keys", headers=auth_headers)
        key_id = list_resp.json()["items"][0]["id"]
        resp = await client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)
        assert resp.status_code == 204
        get_resp = await client.get(f"/api/v1/api-keys/{key_id}", headers=auth_headers)
        assert get_resp.json()["is_active"] is False


class TestAuth:
    async def test_no_auth_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/api-keys")
        assert resp.status_code == 401

    async def test_invalid_key_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/api-keys", headers={"Authorization": "Bearer invalid-key"})
        assert resp.status_code == 401


class TestRateLimit:
    async def test_rate_limit_exceeded(self, client: AsyncClient, seed_api_key):
        from src.config import settings
        original = settings.api_rate_limit_professional
        settings.api_rate_limit_professional = 3
        settings.api_rate_window_seconds = 10
        headers = {"Authorization": "Bearer test-mf-key-123"}
        for _ in range(3):
            resp = await client.get("/api/v1/api-keys", headers=headers)
            assert resp.status_code == 200
        resp = await client.get("/api/v1/api-keys", headers=headers)
        assert resp.status_code == 429
        settings.api_rate_limit_professional = original

    async def test_rate_limit_per_tier(self, client: AsyncClient, seed_api_key, test_session_factory):
        from src.config import settings
        original = settings.api_rate_limit_solo
        settings.api_rate_limit_solo = 1
        settings.api_rate_window_seconds = 10
        solo_key_hash = hash_api_key("solo-test-key")
        async with test_session_factory() as session:
            session.add(APIKey(key_hash=solo_key_hash, name="Solo Key", scopes=["*"], tier="solo"))
            await session.commit()
        headers = {"Authorization": "Bearer solo-test-key"}
        resp = await client.get("/api/v1/api-keys", headers=headers)
        assert resp.status_code == 200
        resp = await client.get("/api/v1/api-keys", headers=headers)
        assert resp.status_code == 429
        settings.api_rate_limit_solo = original


class TestWebhooks:
    async def test_create_webhook(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/webhooks", json={"url": "https://hooks.make.com/example", "events": ["lead.match"]}, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://hooks.make.com/example"
        assert data["events"] == ["lead.match"]
        assert data["is_active"] is True

    async def test_create_webhook_invalid_event(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/webhooks", json={"url": "https://hooks.make.com/example", "events": ["invalid.event"]}, headers=auth_headers)
        assert resp.status_code == 400

    async def test_create_webhook_empty_events(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.post("/api/v1/webhooks", json={"url": "https://hooks.make.com/example", "events": []}, headers=auth_headers)
        assert resp.status_code == 400

    async def test_list_webhooks(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.get("/api/v1/webhooks", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["items"], list)

    async def test_get_webhook(self, client: AsyncClient, seed_api_key, auth_headers):
        create_resp = await client.post("/api/v1/webhooks", json={"url": "https://hooks.make.com/get-test", "events": ["trend.alert"]}, headers=auth_headers)
        wh_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/webhooks/{wh_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == wh_id

    async def test_get_webhook_not_found(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.get("/api/v1/webhooks/nonexistent", headers=auth_headers)
        assert resp.status_code == 404

    async def test_update_webhook(self, client: AsyncClient, seed_api_key, auth_headers):
        create_resp = await client.post("/api/v1/webhooks", json={"url": "https://hooks.make.com/update-test", "events": ["lead.match"]}, headers=auth_headers)
        wh_id = create_resp.json()["id"]
        resp = await client.patch(f"/api/v1/webhooks/{wh_id}", json={"is_active": False}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    async def test_delete_webhook(self, client: AsyncClient, seed_api_key, auth_headers):
        create_resp = await client.post("/api/v1/webhooks", json={"url": "https://hooks.make.com/delete-test", "events": ["lead.match"]}, headers=auth_headers)
        wh_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/webhooks/{wh_id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_webhook_not_accessible_cross_key(self, client: AsyncClient, seed_api_key, auth_headers, test_session_factory):
        create_resp = await client.post("/api/v1/webhooks", json={"url": "https://hooks.make.com/cross-key", "events": ["lead.match"]}, headers=auth_headers)
        wh_id = create_resp.json()["id"]
        other_key_hash = hash_api_key("other-key")
        async with test_session_factory() as session:
            session.add(APIKey(key_hash=other_key_hash, name="Other Key", scopes=["*"], tier="solo"))
            await session.commit()
        resp = await client.get(f"/api/v1/webhooks/{wh_id}", headers={"Authorization": "Bearer other-key"})
        assert resp.status_code == 404


class TestEndpoints:
    async def test_me_endpoint(self, client: AsyncClient, seed_api_key, auth_headers):
        resp = await client.get("/api/v1/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["service"] == "Mandate Finder API"
