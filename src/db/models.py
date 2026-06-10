from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(UTC)


def new_uuid():
    return str(uuid.uuid4())


class MetricEvent(Base):
    __tablename__ = "metric_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    metric_type: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    labels: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, server_default=func.now(), index=True)


class AlertConfig(Base):
    __tablename__ = "alert_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    metric_type: Mapped[str] = mapped_column(String(100), index=True)
    condition: Mapped[str] = mapped_column(String(20))
    threshold: Mapped[float] = mapped_column(Float)
    window_minutes: Mapped[int] = mapped_column(default=15)
    slack_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    tier: Mapped[str] = mapped_column(String(32), default="solo")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    webhooks: Mapped[list[Webhook]] = relationship("Webhook", back_populates="api_key", cascade="all, delete-orphan")


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    api_key_id: Mapped[str] = mapped_column(String(36), ForeignKey("api_keys.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    events: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, server_default=func.now())

    api_key: Mapped[APIKey] = relationship("APIKey", back_populates="webhooks")
    deliveries: Mapped[list[WebhookDelivery]] = relationship("WebhookDelivery", back_populates="webhook", cascade="all, delete-orphan")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    webhook_id: Mapped[str] = mapped_column(String(36), ForeignKey("webhooks.id"), nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, server_default=func.now())

    webhook: Mapped[Webhook] = relationship("Webhook", back_populates="deliveries")
