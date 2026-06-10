import time

from fastapi import Depends, HTTPException
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from src.api.deps import get_current_api_key
from src.config import settings
from src.db.models import APIKey


def _get_tier_limit(tier: str) -> int:
    return {
        "solo": settings.api_rate_limit_solo,
        "professional": settings.api_rate_limit_professional,
        "agency": settings.api_rate_limit_agency,
    }.get(tier, settings.api_rate_limit_solo)

_limiter_instance: "InMemoryRateLimiter | None" = None


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = {}

    async def check(self, key: str, limit: int, window: int) -> bool:
        now = time.time()
        cutoff = now - window
        timestamps = [t for t in self._buckets.get(key, []) if t > cutoff]
        if len(timestamps) >= limit:
            return False
        timestamps.append(now)
        self._buckets[key] = timestamps
        return True

    async def close(self) -> None:
        self._buckets.clear()


def get_rate_limiter() -> InMemoryRateLimiter:
    global _limiter_instance
    if _limiter_instance is None:
        _limiter_instance = InMemoryRateLimiter()
    return _limiter_instance


async def authenticated_api_key(
    api_key: APIKey = Depends(get_current_api_key),
    limiter: InMemoryRateLimiter = Depends(get_rate_limiter),
) -> APIKey:
    tier = api_key.tier
    limit = _get_tier_limit(tier)
    window = settings.api_rate_window_seconds
    allowed = await limiter.check(f"rate_limit:{api_key.id}", limit, window)
    if not allowed:
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(window)},
        )
    return api_key
