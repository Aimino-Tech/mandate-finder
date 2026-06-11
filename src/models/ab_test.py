import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(100))
    role_seniority: Mapped[str | None] = mapped_column(String(50))
    company_size: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    variants: Mapped[list["MessageVariant"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    ab_tests: Mapped[list["ABTest"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class MessageVariant(Base):
    __tablename__ = "message_variants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"))
    name: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    call_to_action: Mapped[str | None] = mapped_column(String(200))
    personalization_level: Mapped[str] = mapped_column(String(50), default="low")
    channel: Mapped[str] = mapped_column(String(50), default="email")
    is_control: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    campaign: Mapped["Campaign"] = relationship(back_populates="variants")
    events: Mapped[list["MessageEvent"]] = relationship(back_populates="variant", cascade="all, delete-orphan")
    ab_test_entries: Mapped[list["ABTestVariant"]] = relationship(back_populates="variant", cascade="all, delete-orphan")


class ABTest(Base):
    __tablename__ = "ab_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"))
    name: Mapped[str] = mapped_column(String(255))
    metric: Mapped[str] = mapped_column(String(50), default="reply_rate")
    significance_threshold: Mapped[float] = mapped_column(Float, default=0.05)
    min_sample_size: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(50), default="running")
    winning_variant_id: Mapped[str | None] = mapped_column(ForeignKey("message_variants.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    campaign: Mapped["Campaign"] = relationship(back_populates="ab_tests")
    winning_variant: Mapped["MessageVariant | None"] = relationship(foreign_keys=[winning_variant_id])
    variants: Mapped[list["ABTestVariant"]] = relationship(back_populates="ab_test", cascade="all, delete-orphan")


class ABTestVariant(Base):
    __tablename__ = "ab_test_variants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ab_test_id: Mapped[str] = mapped_column(ForeignKey("ab_tests.id"))
    variant_id: Mapped[str] = mapped_column(ForeignKey("message_variants.id"))

    ab_test: Mapped["ABTest"] = relationship(back_populates="variants")
    variant: Mapped["MessageVariant"] = relationship(back_populates="ab_test_entries")


class MessageEvent(Base):
    __tablename__ = "message_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    variant_id: Mapped[str] = mapped_column(ForeignKey("message_variants.id"))
    recipient: Mapped[str] = mapped_column(String(255))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meeting_booked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    variant: Mapped["MessageVariant"] = relationship(back_populates="events")


class SendTimeRecommendation(Base):
    __tablename__ = "send_time_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    persona_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    optimal_hour_utc: Mapped[int] = mapped_column(Integer)
    optimal_day_of_week: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
