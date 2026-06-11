from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mandate_finder.database import Base


class DedupCache(Base):
    __tablename__ = "dedup_cache"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    fingerprint_md5: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    source_job_ids: Mapped[dict[str, list[str]]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    merged_job_posting_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_postings.id", ondelete="SET NULL"), nullable=True
    )
    dedup_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NEW"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )
