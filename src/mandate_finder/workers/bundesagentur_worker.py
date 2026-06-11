"""Bundesagentur für Arbeit job ingestion worker.

Taskiq-based periodic worker that polls the BA API, normalizes results,
and stores them via the job repository.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.config import settings
from mandate_finder.integrations.bundesagentur.client import (
    BundesagenturClient,
    BundesagenturClientError,
    BundesagenturRateLimitError,
)
from mandate_finder.integrations.bundesagentur.parser import parse_job_response
from mandate_finder.models.job_posting import JobPosting

logger = logging.getLogger(__name__)

# Rate limit tracking per worker instance
_BA_REQUEST_COUNT: int = 0
_BA_RESET_TIME: datetime | None = None
_BA_DAILY_LIMIT: int = 1000


class BundesagenturJobWorker:
    """Worker that periodically ingests job postings from the BA API.

    Handles rate limiting (1000 req/day), incremental ingestion via
    dedup by source_job_id, and configurable search profiles.
    """

    def __init__(
        self,
        db: AsyncSession,
        keywords: str = "Software Engineer",
        location: str = "",
        max_pages: int = 5,
        page_size: int = 25,
    ) -> None:
        self.db = db
        self.keywords = keywords
        self.location = location
        self.max_pages = max_pages
        self.page_size = min(page_size, 100)
        self.client = BundesagenturClient()
        self._stats: dict[str, int] = {
            "fetched": 0,
            "ingested": 0,
            "skipped": 0,
            "errors": 0,
            "pages": 0,
        }

    async def ingest(self) -> dict[str, int]:
        """Run a full ingestion cycle: fetch, parse, dedup, store."""
        if not settings.ba_configured:
            logger.warning("BA API not configured — skipping ingestion")
            return self._stats

        try:
            for page in range(1, self.max_pages + 1):
                if not self._can_request():
                    logger.warning("BA daily rate limit reached — stopping")
                    break

                page_stats = await self._ingest_page(page)
                self._stats["fetched"] += page_stats["fetched"]
                self._stats["ingested"] += page_stats["ingested"]
                self._stats["skipped"] += page_stats["skipped"]
                self._stats["errors"] += page_stats["errors"]
                self._stats["pages"] += 1

                if page_stats["fetched"] == 0:
                    logger.info("No more results at page %d — stopping", page)
                    break

        except BundesagenturRateLimitError:
            logger.warning("BA API rate limit hit during ingestion")
            self._stats["errors"] += 1
        except BundesagenturClientError as exc:
            logger.error("BA API error during ingestion: %s", exc)
            self._stats["errors"] += 1
        finally:
            await self.client.close()

        logger.info(
            "BA ingestion complete: fetched=%d ingested=%d skipped=%d errors=%d pages=%d",
            self._stats["fetched"],
            self._stats["ingested"],
            self._stats["skipped"],
            self._stats["errors"],
            self._stats["pages"],
        )
        return self._stats

    async def _ingest_page(self, page: int) -> dict[str, int]:
        """Fetch, parse, and store a single page of results."""
        global _BA_REQUEST_COUNT
        stats = {"fetched": 0, "ingested": 0, "skipped": 0, "errors": 0}

        try:
            data = await self.client.search_jobs(
                keywords=self.keywords,
                location=self.location,
                page=page,
                page_size=self.page_size,
            )
            _BA_REQUEST_COUNT += 1
            _update_rate_limit_window()
        except BundesagenturClientError as exc:
            logger.error("Page %d fetch failed: %s", page, exc)
            stats["errors"] += 1
            return stats

        records = parse_job_response(data)
        stats["fetched"] = len(records)

        for record in records:
            try:
                if await self._record_exists(record["source_job_id"]):
                    stats["skipped"] += 1
                    continue

                job = self._build_job(record)
                self.db.add(job)
                stats["ingested"] += 1
            except Exception as exc:
                logger.error("Failed to process record %s: %s", record.get("source_job_id"), exc)
                stats["errors"] += 1

        if stats["ingested"] > 0:
            await self.db.commit()

        return stats

    async def _record_exists(self, source_job_id: str) -> bool:
        """Check if a job posting with this source_job_id already exists."""
        if not source_job_id:
            return False
        result = await self.db.execute(
            select(JobPosting).where(JobPosting.source_job_id == source_job_id)
        )
        return result.scalar_one_or_none() is not None

    def _build_job(self, record: dict) -> JobPosting:
        """Build a JobPosting model instance from a parsed record."""
        return JobPosting(
            source="bundesagentur",
            source_job_id=record.get("source_job_id", ""),
            title=record.get("title", ""),
            company_name=record.get("company_name", ""),
            location_city=record.get("location_city"),
            location_state=record.get("location_state"),
            location=record.get("location"),
            description=record.get("description"),
            occupation_code=record.get("occupation_code"),
            salary_min=record.get("salary_min"),
            salary_max=record.get("salary_max"),
            salary_currency=record.get("salary_currency"),
            employment_type=record.get("employment_type"),
            posted_at=record.get("posted_at"),
            source_url=record.get("source_url"),
            raw_data=record.get("raw_data"),
        )

    def _can_request(self) -> bool:
        """Check if we're still within the daily rate limit."""
        global _BA_REQUEST_COUNT, _BA_RESET_TIME, _BA_DAILY_LIMIT
        if _BA_RESET_TIME and datetime.now(timezone.utc) > _BA_RESET_TIME:
            _BA_REQUEST_COUNT = 0
            _BA_RESET_TIME = None
        return _BA_REQUEST_COUNT < _BA_DAILY_LIMIT

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)


def _update_rate_limit_window() -> None:
    """Update the rate limit reset window (resets daily at midnight)."""
    global _BA_RESET_TIME
    if _BA_RESET_TIME is None:
        now = datetime.now(timezone.utc)
        _BA_RESET_TIME = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)


async def periodic_ba_ingestion(db: AsyncSession) -> dict[str, int]:
    """Taskiq-compatible periodic task for BA job ingestion."""
    worker = BundesagenturJobWorker(db=db)
    return await worker.ingest()
