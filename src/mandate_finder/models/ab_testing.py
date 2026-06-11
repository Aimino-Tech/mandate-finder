from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mandate_finder.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageVariant(Base):
    __tablename__ = "message_variants"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("outreach_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    personalization_level: Mapped[str] = mapped_column(String(50), default="low")
    send_count: Mapped[int] = mapped_column(Integer, default=0)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    meeting_count: Mapped[int] = mapped_column(Integer, default=0)
    is_control: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ABTest(Base):
    __tablename__ = "ab_tests"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("outreach_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    control_variant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("message_variants.id", ondelete="SET NULL"), nullable=True
    )
    winning_variant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("message_variants.id", ondelete="SET NULL"), nullable=True
    )
    significance_threshold: Mapped[float] = mapped_column(Float, default=0.05)
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    control_variant: Mapped[MessageVariant | None] = relationship(
        "MessageVariant", foreign_keys=[control_variant_id], post_update=True
    )
    winning_variant: Mapped[MessageVariant | None] = relationship(
        "MessageVariant", foreign_keys=[winning_variant_id], post_update=True
    )


class ReplyEvent(Base):
    __tablename__ = "reply_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("outreach_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("message_variants.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    handled_by_human: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_data: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
