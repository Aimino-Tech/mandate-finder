from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PlanResponse(BaseModel):
    id: UUID
    name: str
    tier: str
    price_monthly_eur: int
    features: dict[str, object]
    is_active: bool

    model_config = {"from_attributes": True}


class SubscribeRequest(BaseModel):
    plan_id: UUID
    stripe_payment_method_id: str | None = None


class SubscribeResponse(BaseModel):
    subscription_id: UUID
    status: str
    trial_end_at: datetime | None = None
    client_secret: str | None = None


class SubscriptionResponse(BaseModel):
    id: UUID
    plan_id: UUID
    plan_name: str | None = None
    status: str
    trial_end_at: datetime | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    canceled_at: datetime | None = None

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: UUID
    amount_eur: int
    vat_percentage: int
    vat_amount: int
    total_eur: int
    status: str
    pdf_url: str | None = None
    paid_at: datetime | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None

    model_config = {"from_attributes": True}


class BillingPortalResponse(BaseModel):
    url: str


class CancelResponse(BaseModel):
    subscription_id: UUID
    status: str
    canceled_at: datetime | None = None


class ChangePlanRequest(BaseModel):
    plan_id: UUID


class ChangePlanResponse(BaseModel):
    subscription_id: UUID
    status: str
    plan_id: UUID
    plan_name: str | None = None
