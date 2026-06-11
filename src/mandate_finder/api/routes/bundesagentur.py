"""API routes for Bundesagentur für Arbeit integration."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.api.deps import DbSession
from mandate_finder.config import settings
from mandate_finder.integrations.bundesagentur.client import (
    BundesagenturClient,
    BundesagenturClientError,
)
from mandate_finder.integrations.bundesagentur.parser import parse_job_response
from mandate_finder.models.job_posting import JobPosting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/ba", tags=["bundesagentur"])


# ─── Request / Response Schemas ──────────────────────────────────────


class SearchRequest(BaseModel):
    keywords: str = ""
    location: str = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)


class IngestRequest(BaseModel):
    keywords: str = "Software Engineer"
    location: str = ""
    max_pages: int = Field(default=3, ge=1, le=20)


class BaStatusResponse(BaseModel):
    configured: bool
    healthy: bool | None = None
    total_jobs: int = 0
    last_ingestion: str | None = None
    sources: list[str] = []


class SearchResponse(BaseModel):
    total: int
    page: int
    jobs: list[dict[str, Any]]


class IngestResponse(BaseModel):
    status: str
    fetched: int = 0
    ingested: int = 0
    skipped: int = 0
    errors: int = 0


# ─── Routes ──────────────────────────────────────────────────────────


@router.post("/search", response_model=SearchResponse)
async def ba_search_jobs(
    request: SearchRequest,
    db: DbSession,
) -> SearchResponse:
    """Search the Bundesagentur für Arbeit job listing API directly.

    Returns raw results without storing them.
    """
    if not settings.ba_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BA API not configured. Set MANDATE_BA_API_KEY.",
        )

    client = BundesagenturClient()
    try:
        data = await client.search_jobs(
            keywords=request.keywords,
            location=request.location,
            page=request.page,
            page_size=request.page_size,
        )
    except BundesagenturClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"BA API request failed: {exc}",
        ) from exc
    finally:
        await client.close()

    records = parse_job_response(data)
    total = data.get("maxErgebnisse", data.get("total", len(records)))

    return SearchResponse(
        total=int(total),
        page=request.page,
        jobs=records,
    )


@router.get("/status", response_model=BaStatusResponse)
async def ba_status(
    db: DbSession,
) -> BaStatusResponse:
    """Check BA integration health and ingestion statistics."""
    health: bool | None = None
    if settings.ba_configured:
        client = BundesagenturClient()
        try:
            health = await client.health_check()
        except Exception:
            health = False
        finally:
            await client.close()

    # Query job stats from the database
    total_result = await db.execute(select(func.count(JobPosting.id)))
    total_jobs: int = total_result.scalar() or 0

    last_result = await db.execute(
        select(JobPosting.ingested_at)
        .order_by(JobPosting.ingested_at.desc())
        .limit(1)
    )
    last_row = last_result.scalar_one_or_none()
    last_ingestion = (
        last_row.isoformat() if last_row else None
    )

    # Get distinct sources
    sources_result = await db.execute(
        select(JobPosting.source).distinct()
    )
    sources = [row[0] for row in sources_result.fetchall() if row[0]]

    return BaStatusResponse(
        configured=settings.ba_configured,
        healthy=health,
        total_jobs=total_jobs,
        last_ingestion=last_ingestion,
        sources=sources,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ba_trigger_ingestion(
    request: IngestRequest,
    db: DbSession,
) -> IngestResponse:
    """Trigger a manual ingestion of BA job postings."""
    if not settings.ba_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BA API not configured. Set MANDATE_BA_API_KEY.",
        )

    from mandate_finder.workers.bundesagentur_worker import BundesagenturJobWorker

    worker = BundesagenturJobWorker(
        db=db,
        keywords=request.keywords,
        location=request.location,
        max_pages=request.max_pages,
    )
    stats = await worker.ingest()

    return IngestResponse(
        status="completed",
        fetched=stats.get("fetched", 0),
        ingested=stats.get("ingested", 0),
        skipped=stats.get("skipped", 0),
        errors=stats.get("errors", 0),
    )
