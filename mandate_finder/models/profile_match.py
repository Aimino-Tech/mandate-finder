import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mandate_finder.db.base import Base


class ProfileMatch(Base):
    __tablename__ = "profile_matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    job_posting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    user_feedback: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
