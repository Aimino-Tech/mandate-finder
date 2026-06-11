"""BA (Bundesagentur für Arbeit) Job Posting model."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mandate_finder.database import Base


class JobPosting(Base):
    """Job posting sourced from the Bundesagentur für Arbeit API."""

    __tablename__ = "job_postings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    source: Mapped[str] = mapped_column(String(64), default="bundesagentur", index=True)
    source_job_id: Mapped[str] = mapped_column(
        "source_id", String(255), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    company_name: Mapped[str] = mapped_column(
        "company", String(255), nullable=False, index=True
    )
    company_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    occupation_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    skills: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str | None] = mapped_column(
        "url", String(2048), nullable=True
    )
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(
        "raw", JSONB, nullable=True
    )
    pipeline_run: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
