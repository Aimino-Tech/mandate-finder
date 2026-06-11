from __future__ import annotations

from typing import Any

import httpx

from mandate_finder.config import settings


class PropelauthClient:
    def __init__(self) -> None:
        self.api_key = settings.propelauth_api_key
        self.auth_url = settings.propelauth_auth_url.rstrip("/")

    async def validate_token(self, token: str) -> dict[str, Any]:
        if not self.api_key.strip():
            raise RuntimeError("Propelauth API key is not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.auth_url}/api/v1/validate_token",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={"token": token},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "user_id": data.get("user_id"),
                "email": data.get("email"),
                "username": data.get("username"),
                "org_id": data.get("org_id"),
                "role": data.get("role"),
            }

    async def login(self, email: str, password: str) -> dict[str, Any]:
        if not self.api_key.strip():
            raise RuntimeError("Propelauth API key is not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.auth_url}/api/v1/auth/login",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"email": email, "password": password},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    async def get_user(self, user_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.auth_url}/api/v1/user",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={"user_id": user_id},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    async def create_user(self, email: str, password: str, username: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.auth_url}/api/v1/user",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"email": email, "password": password, "username": username},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    async def delete_user(self, user_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{self.auth_url}/api/v1/user",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={"user_id": user_id},
            )
            resp.raise_for_status()
