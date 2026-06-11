from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MessageVariantCreate(BaseModel):
    campaign_id: UUID
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)
    cta: str | None = None
    personalization_level: str = "low"
    is_control: bool = False


class MessageVariantUpdate(BaseModel):
    subject: str | None = None
    body: str | None = None
    cta: str | None = None
    personalization_level: str | None = None
    send_count: int | None = None
    open_count: int | None = None
    reply_count: int | None = None
    meeting_count: int | None = None


class MessageVariantResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    subject: str
    body: str
    cta: str | None
    personalization_level: str
    send_count: int
    open_count: int
    reply_count: int
    meeting_count: int
    is_control: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ABTestCreate(BaseModel):
    campaign_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    control_variant_id: UUID | None = None
    significance_threshold: float = 0.05


class ABTestUpdate(BaseModel):
    name: str | None = None
    status: str | None = None  # running, paused, completed
    winning_variant_id: UUID | None = None
    significance_threshold: float | None = None


class ABTestResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    name: str
    control_variant_id: UUID | None
    winning_variant_id: UUID | None
    significance_threshold: float
    status: str
    started_at: datetime
    ended_at: datetime | None

    model_config = {"from_attributes": True}


class ABTestStats(BaseModel):
    variant_id: UUID
    label: str
    n: int
    open_rate: float
    reply_rate: float
    meeting_rate: float
    is_control: bool
    is_winner: bool
    p_value_vs_control: float | None = None


class ABTestDashboard(BaseModel):
    test: ABTestResponse
    variants: list[ABTestStats]
    winning_variant: ABTestStats | None = None
    recommendation: str | None = None


class PromoteVariantRequest(BaseModel):
    variant_id: UUID


class ReplyEventCreate(BaseModel):
    campaign_id: UUID
    message_id: UUID | None = None
    channel: str = Field(..., pattern="^(email|linkedin|phone)$")
    handled_by_human: bool = False
    raw_data: dict[str, object] | None = None


class ReplyEventResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    message_id: UUID | None
    channel: str
    detected_at: datetime
    handled_by_human: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ExportReportResponse(BaseModel):
    test_name: str
    campaign_id: UUID
    variants: list[dict]
    total_n: int
    winner_id: UUID | None
    p_value_threshold: float
    generated_at: datetime
