from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UserMixin


class PlanTier(StrEnum):
    solo = "solo"
    professional = "professional"
    agency = "agency"


class SubscriptionStatus(StrEnum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    incomplete = "incomplete"
    incomplete_expired = "incomplete_expired"
    paused = "paused"
    suspended = "suspended"
    unpaid = "unpaid"


class InvoiceStatus(StrEnum):
    draft = "draft"
    open = "open"
    paid = "paid"
    void = "void"
    uncollectible = "uncollectible"


class Feature(StrEnum):
    search = "search"
    outreach = "outreach"
    analytics = "analytics"
    team_members = "team_members"
    priority_support = "priority_support"
    api_access = "api_access"
    custom_reports = "custom_reports"


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True)
    tier: Mapped[PlanTier] = mapped_column(String(20), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_eur: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    trial_days: Mapped[int] = mapped_column(default=14)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    subscriptions: Mapped[list[Subscription]] = relationship(
        "Subscription", back_populates="plan"
    )


class Subscription(Base, TimestampMixin, UserMixin):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        String(30), default=SubscriptionStatus.trialing
    )
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trial_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )

    plan: Mapped[Plan] = relationship("Plan", back_populates="subscriptions")
    invoices: Mapped[list[Invoice]] = relationship(
        "Invoice", back_populates="subscription"
    )
    events: Mapped[list[SubscriptionEvent]] = relationship(
        "SubscriptionEvent", back_populates="subscription"
    )


class SubscriptionEvent(Base, TimestampMixin):
    __tablename__ = "subscription_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100))
    stripe_event_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    subscription: Mapped[Subscription] = relationship(
        "Subscription", back_populates="events"
    )


class Invoice(Base, TimestampMixin, UserMixin):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id"),
        nullable=False,
        index=True,
    )
    stripe_invoice_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        String(20), default=InvoiceStatus.draft
    )
    total_gross: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_net: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_vat_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    company_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )

    subscription: Mapped[Subscription] = relationship(
        "Subscription", back_populates="invoices"
    )
    line_items: Mapped[list[InvoiceLineItem]] = relationship(
        "InvoiceLineItem", back_populates="invoice"
    )


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price_net: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_net: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    invoice: Mapped[Invoice] = relationship(
        "Invoice", back_populates="line_items"
    )
