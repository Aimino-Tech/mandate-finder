from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mandate_finder.database import Base


class CompanySignal(Base):
    """Aggregated competition signal for a company (k-anonymized).

    Stores the number of unique agencies/competitors targeting a given company,
    computed by the signal_aggregator worker. Counts below 3 are hidden
    (k-anonymity threshold).
    """
    __tablename__ = "company_signals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    competitor_count: Mapped[int] = mapped_column(Integer, default=0)
    trend: Mapped[str] = mapped_column(String(20), default="stable")  # rising, stable, declining
    last_updated: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
