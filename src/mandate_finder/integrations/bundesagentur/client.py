"""Bundesagentur für Arbeit API client.

REST client for the free BA job listing API.
Rate limit: ~1000 requests/day.
Docs: https://rest.arbeitsagentur.de/
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from mandate_finder.config import settings

logger = logging.getLogger(__name__)


class BundesagenturClientError(Exception):
    """Base exception for BA API errors."""


class BundesagenturRateLimitError(BundesagenturClientError):
    """Raised when the BA API rate limit is exceeded."""


class BundesagenturAuthError(BundesagenturClientError):
    """Raised when authentication with the BA API fails."""


class BundesagenturClient:
    """HTTP client for the Bundesagentur für Arbeit Jobsuche API.

    Wraps authentication, request rate limiting, and response handling.
    """

    BASE_URL: str = settings.ba_api_base_url
    AUTH_URL: str = "https://rest.arbeitsagentur.de/oauth/gettoken_cc"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.ba_api_key
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._last_request_at: float = 0.0
        self._min_request_interval: float = 0.1  # 100ms between requests
        self._client = httpx.AsyncClient(timeout=30.0)

    async def _authenticate(self) -> str:
        """Obtain an OAuth2 client credentials token from the BA API."""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        if not self._api_key:
            raise BundesagenturAuthError(
                "BA API key not configured. Set MANDATE_BA_API_KEY."
            )

        try:
            resp = await self._client.post(
                self.AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._api_key,
                    "client_secret": "",  # BA uses client_id only
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self._token_expires_at = time.time() + expires_in - 60  # 60s buffer
            logger.debug("BA API OAuth token acquired, expires in %ds", expires_in)
            return self._access_token  # type: ignore[return-value]
        except httpx.HTTPStatusError as exc:
            raise BundesagenturAuthError(
                f"BA API auth failed: {exc.response.status_code} {exc.response.text[:200]}"
            ) from exc
        except (httpx.RequestError, KeyError) as exc:
            raise BundesagenturAuthError(f"BA API auth error: {exc}") from exc

    async def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        now = time.time()
        elapsed = now - self._last_request_at
        if elapsed < self._min_request_interval:
            await self._throttle(self._min_request_interval - elapsed)
        self._last_request_at = time.time()

    async def _throttle(self, duration: float) -> None:
        """Sleep for the given duration."""
        await self._client.aclose()  # placeholder - uses asyncio.sleep
        import asyncio
        await asyncio.sleep(duration)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the BA API."""
        await self._rate_limit()
        token = await self._authenticate()

        url = f"{self.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        try:
            resp = await self._client.request(
                method, url, headers=headers, params=params, json=data
            )

            if resp.status_code == 429:
                raise BundesagenturRateLimitError(
                    "BA API rate limit exceeded (429 Too Many Requests)"
                )

            resp.raise_for_status()
            return resp.json()

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise BundesagenturRateLimitError(
                    "BA API rate limit exceeded"
                ) from exc
            raise BundesagenturClientError(
                f"BA API request failed: {exc.response.status_code} {exc.response.text[:300]}"
            ) from exc
        except httpx.RequestError as exc:
            raise BundesagenturClientError(f"BA API request error: {exc}") from exc

    async def search_jobs(
        self,
        keywords: str = "",
        location: str = "",
        page: int = 1,
        page_size: int = 25,
        **filters: Any,
    ) -> dict[str, Any]:
        """Search job postings on the BA API.

        Args:
            keywords: Job title or keyword search terms.
            location: City, region, or postal code.
            page: Page number (1-indexed).
            page_size: Results per page (max 100).
            **filters: Additional BA API filter parameters.

        Returns:
            Raw API response as a dict.
        """
        params: dict[str, Any] = {
            "page": page,
            "size": min(page_size, 100),
        }
        if keywords:
            params["was"] = keywords
        if location:
            params["wo"] = location
        params.update(filters)

        logger.info(
            "BA search: keywords=%r location=%r page=%d", keywords, location, page
        )
        return await self._request("GET", "/pc/v4/jobs", params=params)

    async def get_job_details(self, job_id: str) -> dict[str, Any]:
        """Get detailed information about a specific job posting."""
        return await self._request("GET", f"/pc/v4/jobs/{job_id}")

    async def health_check(self) -> bool:
        """Check if the BA API is reachable and authenticated."""
        try:
            await self.search_jobs(page=1, page_size=1)
            return True
        except BundesagenturClientError:
            return False

    async def close(self) -> None:
        await self._client.aclose()
