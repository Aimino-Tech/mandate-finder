import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class TokenBucketRateLimiter:
    def __init__(self, rate: float = 1.0, burst: int = 5) -> None:
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = self._now()

    @staticmethod
    def _now() -> float:
        try:
            return asyncio.get_running_loop().time()
        except RuntimeError:
            return time.monotonic()

    def _refill(self) -> None:
        now = self._now()
        elapsed = now - self.last_refill
        self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate)
        self.last_refill = now

    async def acquire(self) -> None:
        while True:
            self._refill()
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            await asyncio.sleep((1.0 - self.tokens) / self.rate)


class TierRateLimiter:
    TIERS = {
        "free": {"daily": 100, "monthly": 1000},
        "basic": {"daily": 1000, "monthly": 10000},
        "pro": {"daily": 5000, "monthly": 50000},
    }

    def __init__(self, tier: str = "free") -> None:
        limits = self.TIERS.get(tier, self.TIERS["free"])
        self._limiter = TokenBucketRateLimiter(rate=limits["daily"] / 86400.0, burst=5)
        self.tier = tier

    async def acquire(self) -> None:
        await self._limiter.acquire()

    @asynccontextmanager
    async def throttle(self) -> AsyncIterator[None]:
        await self.acquire()
        yield
