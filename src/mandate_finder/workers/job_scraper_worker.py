"""Taskiq worker for job board scraping using Hermes agents.

Dispatches Hermes agent invocations per source, handles errors per-source
(not globally), and persists results via ScrapRun tracking.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.scraping import ScrapRun, ScrapSource
from mandate_finder.scrapers.job_scraper import JobScraperRegistry, scrape_source
from mandate_finder.schemas.scraping import RawJobData, ScrapRunResult

logger = logging.getLogger(__name__)


async def run_scrape_for_source(
    db: AsyncSession,
    source_name: str,
    search_terms: list[str] | None = None,
) -> ScrapRunResult:
    """Execute a single scrape run for one source and persist results.

    This is designed to be called per-source so that errors in one source
    do not affect others (per-source error handling).
    """
    # Resolve source from DB
    result = await db.execute(
        select(ScrapSource).where(
            ScrapSource.name == source_name,
            ScrapSource.is_active == True,  # noqa: E712
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        return ScrapRunResult(
            run_id=uuid4(),
            source_name=source_name,
            status="failed",
            jobs_found=0,
            jobs_new=0,
            error_count=1,
            duration_seconds=0.0,
        )

    # Create a ScrapRun record
    run = ScrapRun(
        source_id=source.id,
        status="running",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    start_time = time.monotonic()
    error_count = 0
    jobs_found = 0
    jobs_new = 0
    final_status = "completed"

    try:
        raw_jobs: list[RawJobData] = await scrape_source(
            source=source_name,
            search_terms=search_terms,
        )
        jobs_found = len(raw_jobs)

        # In production, raw_jobs would be passed to the pipeline for dedup/ingest
        # For now, we count all as "new"
        jobs_new = jobs_found

    except Exception as exc:
        logger.exception("Scrape failed for source '%s': %s", source_name, exc)
        final_status = "failed"
        error_count = 1
        run.error_details = {"error": str(exc), "type": type(exc).__name__}

    duration = time.monotonic() - start_time

    # Finalize the run record
    run.status = final_status
    run.jobs_found = jobs_found
    run.jobs_new = jobs_new
    run.error_count = error_count
    run.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return ScrapRunResult(
        run_id=run.id,
        source_name=source_name,
        status=final_status,
        jobs_found=jobs_found,
        jobs_new=jobs_new,
        error_count=error_count,
        duration_seconds=round(duration, 3),
    )


async def run_scrape_for_all_sources(
    db: AsyncSession,
    source_names: list[str] | None = None,
    search_terms: list[str] | None = None,
) -> list[ScrapRunResult]:
    """Run scrape for multiple sources. If source_names is None, runs all active.

    Each source is scraped independently so a single failure doesn't stop others.
    """
    if source_names:
        names = source_names
    else:
        names = JobScraperRegistry.active_names()

    results: list[ScrapRunResult] = []
    for name in names:
        result = await run_scrape_for_source(db, name, search_terms)
        results.append(result)

    return results
