"""API routes for job posting dedup & normalization."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.api.deps import DbSession, get_current_user
from mandate_finder.models.dedup_cache import DedupCache
from mandate_finder.models.job_posting import JobPosting
from mandate_finder.scrapers.job_dedup import (
    DedupDecision,
    JobDedupEngine,
    compute_fingerprint,
)
from mandate_finder.scrapers.job_normalizer import JobNormalizer

router = APIRouter(prefix="/dedup", tags=["dedup"], dependencies=[Depends(get_current_user)])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class CheckRequest(BaseModel):
    title: str
    company: str | None = None
    company_name: str | None = None
    location: str | None = None
    description: str | None = None
    source: str | None = None
    source_job_id: str | None = None


class NormalizeRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    text: str | None = None


class NormalizeResponse(BaseModel):
    normalized_title: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    skills: list[str] = Field(default_factory=list)
    employment_type: str | None = None


class IngestRequest(BaseModel):
    source: str
    source_job_id: str | None = None
    title: str
    company_name: str | None = None
    location: str | None = None
    description: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    skills: list[str] | None = None
    employment_type: str | None = None
    posted_at: str | None = None
    source_url: str | None = None
    occupation_code: str | None = None


class IngestResponse(BaseModel):
    id: str
    decision: str
    confidence: float
    fingerprint_md5: str | None = None


class CheckResponse(BaseModel):
    decision: str
    existing_id: str | None = None
    confidence: float
    detail: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _fetch_existing_postings(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(
        select(JobPosting).where(JobPosting.is_active.is_(True))
    )
    rows = result.scalars().all()
    return [_row_to_dict(r) for r in rows]


async def _fetch_cache_entries(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(select(DedupCache))
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "fingerprint_md5": r.fingerprint_md5,
            "merged_job_posting_id": str(r.merged_job_posting_id) if r.merged_job_posting_id else None,
            "confidence": r.confidence,
        }
        for r in rows
    ]


def _row_to_dict(row: JobPosting) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "source": row.source,
        "source_job_id": row.source_job_id,
        "title": row.title,
        "normalized_title": row.normalized_title,
        "company_name": row.company_name,
        "location": row.location,
        "description": row.description,
        "salary_min": row.salary_min,
        "salary_max": row.salary_max,
        "salary_currency": row.salary_currency,
        "skills": row.skills or [],
        "employment_type": row.employment_type,
        "source_url": row.source_url,
        "fingerprint_md5": row.fingerprint_md5,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/check", response_model=CheckResponse)
async def dedup_check(
    data: CheckRequest,
    db: DbSession,
) -> CheckResponse:
    """Check a job posting against the dedup engine without persisting."""
    posting: dict[str, Any] = {
        "title": data.title,
        "normalized_title": None,
        "company_name": data.company_name or data.company,
        "location": data.location,
        "description": data.description,
        "source": data.source,
        "source_job_id": data.source_job_id,
    }

    existing = await _fetch_existing_postings(db)
    cache_entries = await _fetch_cache_entries(db)

    engine = JobDedupEngine()
    result = await engine.check_new(posting, existing=existing, cache_entries=cache_entries)

    return CheckResponse(
        decision=result.decision.value,
        existing_id=str(result.existing_id) if result.existing_id else None,
        confidence=result.confidence,
        detail=result.detail,
    )


@router.post("/normalize", response_model=NormalizeResponse)
async def dedup_normalize(
    data: NormalizeRequest,
) -> NormalizeResponse:
    """Normalize a job posting's fields (title, salary, skills, employment type)."""
    normalizer = JobNormalizer()
    text = data.text or data.description or ""

    normalized_title: str | None = None
    if data.title:
        normalized_title = normalizer.normalize_title(data.title)

    salary_info = normalizer.extract_salary(text)
    skills = normalizer.extract_skills(text)
    emp_type = normalizer.classify_employment_type(text)

    return NormalizeResponse(
        normalized_title=normalized_title,
        salary_min=salary_info.get("salary_min"),  # type: ignore[arg-type]
        salary_max=salary_info.get("salary_max"),  # type: ignore[arg-type]
        salary_currency=salary_info.get("salary_currency"),  # type: ignore[arg-type]
        skills=skills,
        employment_type=emp_type,
    )


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def dedup_ingest(
    data: IngestRequest,
    db: DbSession,
) -> IngestResponse:
    """Normalize, dedup-check, and persist a job posting."""
    normalizer = JobNormalizer()

    # 1. Normalize
    normalized_title = normalizer.normalize_title(data.title)
    salary_info = normalizer.extract_salary(data.description or "")
    skills = data.skills or normalizer.extract_skills(data.description or "")
    emp_type = data.employment_type or normalizer.classify_employment_type(
        f"{data.title} {data.description or ''}"
    )

    posting: dict[str, Any] = {
        "source": data.source,
        "source_job_id": data.source_job_id,
        "title": data.title,
        "normalized_title": normalized_title,
        "company_name": data.company_name,
        "location": data.location,
        "description": data.description,
        "salary_min": data.salary_min or salary_info.get("salary_min"),
        "salary_max": data.salary_max or salary_info.get("salary_max"),
        "salary_currency": data.salary_currency or salary_info.get("salary_currency"),
        "skills": skills,
        "employment_type": emp_type,
        "source_url": data.source_url,
        "occupation_code": data.occupation_code,
    }

    # 2. Compute fingerprint
    posting["fingerprint_md5"] = compute_fingerprint(posting)

    # 3. Dedup check
    existing = await _fetch_existing_postings(db)
    cache_entries = await _fetch_cache_entries(db)
    engine = JobDedupEngine()
    result = await engine.check_new(posting, existing=existing, cache_entries=cache_entries)

    # 4. Persist or merge
    if result.decision in (DedupDecision.EXISTING, DedupDecision.FINGERPRINT, DedupDecision.CACHE) and result.existing_id:
        return IngestResponse(
            id=str(result.existing_id),
            decision=result.decision.value,
            confidence=result.confidence,
            fingerprint_md5=posting["fingerprint_md5"],
        )

    if result.decision == DedupDecision.MERGED and result.existing_id:
        existing_row = await db.get(JobPosting, result.existing_id)
        if existing_row:
            merged = await engine.merge_job_postings(
                _row_to_dict(existing_row), posting
            )
            for key, value in merged.items():
                if key in ("id", "created_at", "updated_at", "_merged_from"):
                    continue
                setattr(existing_row, key, value)
            await db.commit()
            await db.refresh(existing_row)
            return IngestResponse(
                id=str(existing_row.id),
                decision=result.decision.value,
                confidence=result.confidence,
                fingerprint_md5=posting["fingerprint_md5"],
            )

    # 5. Create new JobPosting
    job = JobPosting(
        source=data.source,
        source_job_id=data.source_job_id,
        title=data.title,
        normalized_title=normalized_title,
        company_name=data.company_name,
        location=data.location,
        description=data.description,
        salary_min=posting["salary_min"],
        salary_max=posting["salary_max"],
        salary_currency=posting["salary_currency"],
        skills=skills,
        employment_type=emp_type,
        source_url=data.source_url,
        occupation_code=data.occupation_code,
        fingerprint_md5=posting["fingerprint_md5"],
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return IngestResponse(
        id=str(job.id),
        decision=DedupDecision.NEW.value,
        confidence=1.0,
        fingerprint_md5=job.fingerprint_md5,
    )
