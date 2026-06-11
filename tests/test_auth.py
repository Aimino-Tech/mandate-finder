from __future__ import annotations

import pytest
from httpx import AsyncClient

from mandate_finder.config import settings


@pytest.mark.asyncio
async def test_auth_public_config(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/auth/config")
    assert response.status_code == 200
    data = response.json()
    assert data["demo_login_available"] is True
    assert data["propelauth_configured"] is False
    assert data["propelauth_login_url"] is None


@pytest.mark.asyncio
async def test_login_dev_token(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@test.com", "password": "test"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"] == settings.dev_auth_token
    assert data["user_id"] == "local-dev-user"


@pytest.mark.asyncio
async def test_logout(async_client: AsyncClient) -> None:
    response = await async_client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_users_me_no_token(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_users_me_invalid_token(async_client: AsyncClient) -> None:
    response = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_users_me_creates_user(
    async_client: AsyncClient,
) -> None:
    headers = {"Authorization": f"Bearer {settings.dev_auth_token}"}
    response = await async_client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "Demo User"
    assert data["email"] == "demo@mandate.local"


@pytest.mark.asyncio
async def test_register_dev_mode(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@test.com", "password": "test123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"] == settings.dev_auth_token
    assert data["user_id"] == "local-dev-user"
