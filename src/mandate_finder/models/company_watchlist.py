from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mandate_finder.database import Base


class CompanyWatchlist(Base):
    """User watchlist entry for monitoring a company's competitive activity."""

    __tablename__ = "company_watchlists"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    notify_on_change: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
