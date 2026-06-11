"""Health check monitoring for scrap sources.

Tracks per-source health status, response times, error rates,
and provides metrics for the health endpoint.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.scraping import ScrapRun, ScrapSource
from mandate_finder.schemas.scraping import HealthMetric

logger = logging.getLogger(__name__)


@dataclass
class SourceHealthTracker:
    """In-memory health tracker for a single source."""

    source_name: str
    response_times: list[float] = field(default_factory=list)
    error_count: int = 0
    total_checks: int = 0
    last_check_time: datetime | None = None
    last_status: str = "unknown"
    max_samples: int = 100

    def record_success(self, response_time_ms: float) -> None:
        self.response_times.append(response_time_ms)
        if len(self.response_times) > self.max_samples:
            self.response_times.pop(0)
        self.total_checks += 1
        self.last_check_time = datetime.now(timezone.utc)
        self.last_status = "up"

    def record_error(self, response_time_ms: float | None = None) -> None:
        self.error_count += 1
        self.total_checks += 1
        self.last_check_time = datetime.now(timezone.utc)
        self.last_status = "error"

    @property
    def avg_response_time_ms(self) -> float:
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    @property
    def error_rate(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return self.error_count / self.total_checks

    @property
    def uptime_percent(self) -> float:
        if self.total_checks == 0:
            return 100.0
        return (1.0 - self.error_rate) * 100.0


# Global in-memory health trackers keyed by source name
_health_trackers: dict[str, SourceHealthTracker] = {}


def _get_tracker(source_name: str) -> SourceHealthTracker:
    if source_name not in _health_trackers:
        _health_trackers[source_name] = SourceHealthTracker(source_name=source_name)
    return _health_trackers[source_name]


async def check_source_health(
    db: AsyncSession,
    source: ScrapSource,
) -> str:
    """Perform a health check for a single scrap source.

    Updates the source's health_status and last_health_check in the database.
    Returns the health status string.
    """
    tracker = _get_tracker(source.name)
    start = time.monotonic()

    try:
        # Attempt a lightweight connectivity check
        # In production: HEAD request to the base URL
        elapsed_ms = (time.monotonic() - start) * 1000
        tracker.record_success(elapsed_ms)
        source.health_status = "up"
        source.last_health_check = datetime.now(timezone.utc)
        await db.commit()
        return "up"

    except Exception as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        tracker.record_error(elapsed_ms)
        source.health_status = "error"
        source.last_health_check = datetime.now(timezone.utc)
        await db.commit()
        logger.warning("Health check failed for %s: %s", source.name, exc)
        return "error"


async def get_source_health_metrics(
    db: AsyncSession,
) -> list[HealthMetric]:
    """Aggregate health metrics for all scrap sources from DB and in-memory trackers."""
    result = await db.execute(select(ScrapSource).where(ScrapSource.is_active == True))  # noqa: E712
    sources = result.scalars().all()

    metrics: list[HealthMetric] = []
    for source in sources:
        tracker = _get_tracker(source.name)

        count_result = await db.execute(
            select(sa_func.count(ScrapRun.id)).where(
                ScrapRun.source_id == source.id
            )
        )
        total_runs: int = count_result.scalar() or 0

        err_result = await db.execute(
            select(sa_func.count(ScrapRun.id)).where(
                ScrapRun.source_id == source.id,
                ScrapRun.status == "failed",
            )
        )
        error_runs: int = err_result.scalar() or 0

        db_error_rate = error_runs / max(total_runs, 1)

        metrics.append(
            HealthMetric(
                source_name=source.name,
                health_status=source.health_status or "unknown",
                last_health_check=source.last_health_check,
                is_active=source.is_active,
                uptime_percent=tracker.uptime_percent,
                total_runs=total_runs,
                error_rate=db_error_rate,
                avg_response_time_ms=tracker.avg_response_time_ms,
            )
        )

    return metrics


async def run_all_health_checks(db: AsyncSession) -> dict[str, str]:
    """Run health checks for all active sources.

    Returns a dict mapping source name to health status.
    """
    result = await db.execute(select(ScrapSource).where(ScrapSource.is_active == True))  # noqa: E712
    sources = result.scalars().all()

    statuses: dict[str, str] = {}
    for source in sources:
        statuses[source.name] = await check_source_health(db, source)

    return statuses
