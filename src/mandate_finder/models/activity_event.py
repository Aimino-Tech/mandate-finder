from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mandate_finder.database import Base


class ActivityEvent(Base):
    """Record of a user's activity targeting a company.

    Used to compute competitor counts per company.
    When is_private is True, the event is excluded from aggregation.
    """

    __tablename__ = "activity_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    company_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # outreach, applied, viewed
    occurred_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
