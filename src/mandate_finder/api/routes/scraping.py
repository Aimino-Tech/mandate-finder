"""API routes for job board scraping management.

Provides endpoints to trigger scrapes, list sources, list runs,
and check source health.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uuid import UUID

from mandate_finder.api.deps import DbSession
from mandate_finder.database import get_db
from mandate_finder.models.scraping import ScrapRun, ScrapSource
from mandate_finder.schemas.scraping import (
    HealthMetric,
    ScrapRunRequest,
    ScrapRunResponse,
    ScrapRunResult,
    ScrapSourceResponse,
)
from mandate_finder.scrapers.source_health import get_source_health_metrics
from mandate_finder.workers.job_scraper_worker import run_scrape_for_all_sources

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scrap", tags=["scraping"])


@router.post("/run", response_model=list[ScrapRunResult])
async def trigger_scrape(
    body: ScrapRunRequest,
    db: DbSession,
) -> list[ScrapRunResult]:
    """Trigger a scrape run for one or more sources.

    If source_names is omitted or empty, all active sources are scraped.
    Each source runs independently; errors are per-source.
    """
    results = await run_scrape_for_all_sources(
        db=db,
        source_names=body.source_names,
        search_terms=body.search_terms,
    )
    return results


@router.get("/sources", response_model=list[ScrapSourceResponse])
async def list_sources(
    db: DbSession,
) -> list[ScrapSourceResponse]:
    """List all registered scrap sources."""
    result = await db.execute(
        select(ScrapSource).order_by(ScrapSource.name)
    )
    sources = result.scalars().all()
    return [ScrapSourceResponse.model_validate(s) for s in sources]


@router.get("/runs", response_model=list[ScrapRunResponse])
async def list_runs(
    db: DbSession,
    limit: int = 50,
    offset: int = 0,
) -> list[ScrapRunResponse]:
    """List recent scrape runs."""
    result = await db.execute(
        select(ScrapRun)
        .order_by(ScrapRun.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    runs = result.scalars().all()
    return [ScrapRunResponse.model_validate(r) for r in runs]


@router.get("/health", response_model=list[HealthMetric])
async def source_health(
    db: DbSession,
) -> list[HealthMetric]:
    """Get health metrics for all scrap sources."""
    metrics = await get_source_health_metrics(db)
    return metrics


# -- Admin endpoints for source management --

@router.post("/sources", response_model=ScrapSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    db: DbSession,
    name: str,
    base_url: str,
    rate_limit_per_minute: int = 30,
) -> ScrapSourceResponse:
    """Register a new scrap source (admin)."""
    source = ScrapSource(
        name=name,
        base_url=base_url,
        rate_limit_per_minute=rate_limit_per_minute,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return ScrapSourceResponse.model_validate(source)


@router.patch("/sources/{source_id}/toggle", response_model=ScrapSourceResponse)
async def toggle_source(
    source_id: UUID,
    db: DbSession,
) -> ScrapSourceResponse:
    """Toggle a source's active state."""
    result = await db.execute(
        select(ScrapSource).where(ScrapSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.is_active = not source.is_active
    await db.commit()
    await db.refresh(source)
    return ScrapSourceResponse.model_validate(source)
