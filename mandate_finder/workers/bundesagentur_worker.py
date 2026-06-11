import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from mandate_finder.integrations.bundesagentur.client import BundesagenturClient
from mandate_finder.models.job_posting import JobPosting

logger = logging.getLogger(__name__)


class BundesagenturJobWorker:
    def __init__(
        self,
        api_key: str,
        db_session_factory: Any,
        keywords: list[str] | None = None,
        location: str | None = None,
        poll_interval_seconds: int = 86400,
        daily_limit: int = 1000,
    ) -> None:
        self._client = BundesagenturClient(api_key, daily_limit=daily_limit)
        self._db_session_factory = db_session_factory
        self._keywords = keywords or ["Senior React"]
        self._location = location
        self._poll_interval = poll_interval_seconds
        self._running = False

    async def run_once(self) -> dict[str, int]:
        total_ingested = 0
        total_failed = 0
        total_new = 0
        total_updated = 0

        for keyword in self._keywords:
            page = 0
            while True:
                try:
                    jobs = await self._client.search_jobs(keyword, self._location, page=page)
                except Exception:
                    logger.exception("BA API search failed for keyword=%s page=%d", keyword, page)
                    total_failed += 1
                    break

                if not jobs:
                    break

                new, updated = await self._upsert_jobs(jobs)
                total_new += new
                total_updated += updated
                total_ingested += len(jobs)
                page += 1

        return {
            "ingested": total_ingested,
            "new": total_new,
            "updated": total_updated,
            "failed": total_failed,
        }

    async def _upsert_jobs(self, jobs: list[dict[str, Any]]) -> tuple[int, int]:
        async with self._db_session_factory() as session:
            new_count = 0
            updated_count = 0

            for job in jobs:
                stmt = pg_insert(JobPosting).values(
                    ba_job_id=job["ba_job_id"],
                    title=job["title"],
                    company_name=job["company_name"],
                    location_city=job.get("location_city"),
                    location_state=job.get("location_state"),
                    description=job.get("description"),
                    occupation_code=job.get("occupation_code"),
                    employment_type=job.get("employment_type", "other"),
                    source_url=job.get("source_url"),
                    posted_at=job.get("posted_at"),
                    last_modified=job.get("last_modified", datetime.now(timezone.utc)),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ba_job_id"],
                    set_={
                        "title": stmt.excluded.title,
                        "company_name": stmt.excluded.company_name,
                        "location_city": stmt.excluded.location_city,
                        "location_state": stmt.excluded.location_state,
                        "description": stmt.excluded.description,
                        "occupation_code": stmt.excluded.occupation_code,
                        "employment_type": stmt.excluded.employment_type,
                        "source_url": stmt.excluded.source_url,
                        "posted_at": stmt.excluded.posted_at,
                        "last_modified": stmt.excluded.last_modified,
                        "is_active": True,
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                result = await session.execute(stmt)
                if result.inserted_primary_key:
                    new_count += 1
                else:
                    updated_count += 1

            await session.commit()

        return new_count, updated_count

    async def run_forever(self) -> None:
        self._running = True
        logger.info("Starting BA worker with %d keywords, poll interval=%ds", len(self._keywords), self._poll_interval)

        while self._running:
            stats = await self.run_once()
            logger.info("BA worker cycle complete: %s", stats)
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        self._running = False
        await self._client.close()
