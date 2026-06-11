from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ScrapSourceResponse(BaseModel):
    id: UUID
    name: str
    base_url: str
    rate_limit_per_minute: int
    is_active: bool
    health_status: str
    last_health_check: datetime | None
    config: dict[str, object]
    created_at: datetime

    model_config = {"from_attributes": True}


class ScrapRunResponse(BaseModel):
    id: UUID
    source_id: UUID
    status: str
    jobs_found: int
    jobs_new: int
    error_count: int
    error_details: dict[str, object] | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ScrapRunRequest(BaseModel):
    source_names: list[str] | None = None
    search_terms: list[str] | None = None


class ScrapRunResult(BaseModel):
    run_id: UUID
    source_name: str
    status: str
    jobs_found: int
    jobs_new: int
    error_count: int
    duration_seconds: float | None


class HealthMetric(BaseModel):
    source_name: str
    health_status: str
    last_health_check: datetime | None
    is_active: bool
    uptime_percent: float
    total_runs: int
    error_rate: float
    avg_response_time_ms: float


class RawJobData(BaseModel):
    """Normalized raw job data extracted by a Hermes agent."""

    title: str
    company_name: str
    location: str
    description: str
    source_url: str
    posted_date: str | None = None
    source: str
    external_id: str | None = None
    salary: str | None = None
    job_type: str | None = None
