from typing import Any

import httpx

from src.config import settings


class ApolloClient:
    def __init__(self, api_key: str = "", base_url: str = "https://api.apollo.io/v1") -> None:
        self.api_key = api_key or settings.apollo_api_key; self.base_url = base_url; self._client: httpx.AsyncClient | None = None
    async def _session(self) -> httpx.AsyncClient:
        if self._client is None: self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    async def close(self) -> None:
        if self._client: await self._client.aclose(); self._client = None
    async def enrich_person(self, linkedin_url: str = "", email: str = "") -> dict[str, Any]:
        if not self.api_key: return {"id": None, "error": "Apollo not configured"}
        try:
            body: dict[str, Any] = {"api_key": self.api_key}
            if linkedin_url: body["linkedin_url"] = linkedin_url
            if email: body["email"] = email
            resp = await (await self._session()).post(f"{self.base_url}/people/match", headers={"Content-Type": "application/json"}, json=body)
            resp.raise_for_status(); return resp.json()
        except Exception as e: return {"id": None, "error": str(e)}
    async def search_people(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.api_key: return []
        try:
            resp = await (await self._session()).post(f"{self.base_url}/people/search", headers={"Content-Type": "application/json", "X-API-KEY": self.api_key}, json=query)
            resp.raise_for_status(); return resp.json().get("people", []) or resp.json().get("results", [])
        except Exception: return []
    async def search_organizations(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.api_key: return []
        try:
            resp = await (await self._session()).post(f"{self.base_url}/organizations/search", headers={"Content-Type": "application/json", "X-API-KEY": self.api_key}, json=query)
            resp.raise_for_status(); return resp.json().get("organizations", []) or resp.json().get("results", [])
        except Exception: return []
    async def match_organization(self, domain: str = "", name: str = "") -> dict[str, Any]:
        if not self.api_key: return {"id": None, "error": "Apollo not configured"}
        try:
            body: dict[str, Any] = {"api_key": self.api_key}
            if domain: body["domain"] = domain
            if name: body["organization_name"] = name
            resp = await (await self._session()).post(f"{self.base_url}/organizations/match", headers={"Content-Type": "application/json"}, json=body)
            resp.raise_for_status(); return resp.json().get("organization", {})
        except Exception as e: return {"id": None, "error": str(e)}
    async def verify_email(self, email: str) -> dict[str, Any]:
        if not self.api_key: return {"id": None, "error": "Apollo not configured"}
        try:
            resp = await (await self._session()).post(f"{self.base_url}/people/verify_email", headers={"Content-Type": "application/json", "X-API-KEY": self.api_key}, json={"api_key": self.api_key, "email": email})
            resp.raise_for_status(); return resp.json()
        except Exception as e: return {"error": str(e)}
