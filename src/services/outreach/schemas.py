from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OutreachTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    channel: str = Field(default="email", pattern="^(email|linkedin)$")
    subject_template: str
    body_template: str
    tone: str = "professional"
    variables_schema: list[str] | None = None


class OutreachTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    channel: str | None = Field(default=None, pattern="^(email|linkedin)$")
    subject_template: str | None = None
    body_template: str | None = None
    tone: str | None = None
    is_active: bool | None = None


class OutreachTemplateResponse(BaseModel):
    id: str
    name: str
    description: str | None
    channel: str
    subject_template: str
    body_template: str
    variables_schema: list[str] | None
    tone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PreviewRequest(BaseModel):
    variables: dict[str, str]


class PreviewResponse(BaseModel):
    subject: str
    body_text: str


class CampaignCreate(BaseModel):
    name: str
    target_company_name: str
    target_company_domain: str = ""
    target_industry: str | None = None
    tone: str = "professional"


class CampaignUpdate(BaseModel):
    name: str | None = None
    target_company_name: str | None = None
    target_company_domain: str | None = None
    target_industry: str | None = None
    tone: str | None = None
    status: str | None = None


class CampaignResponse(BaseModel):
    id: str
    name: str
    target_company_name: str
    target_company_domain: str
    target_industry: str | None
    tone: str
    status: str
    total_messages: int
    sent_count: int
    opened_count: int
    replied_count: int
    bounced_count: int
    scheduled_at: datetime | None
    sent_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RecipientCreate(BaseModel):
    first_name: str
    last_name: str
    title: str
    email: str
    phone: str | None = None
    linkedin_url: str | None = None
    company_name: str | None = None
    confidence_score: float = 0.0
    source_enrichment_id: str | None = None


class RecipientResponse(BaseModel):
    id: str
    campaign_id: str | None
    first_name: str
    last_name: str
    title: str
    email: str
    phone: str | None
    linkedin_url: str | None
    company_name: str
    company_domain: str
    confidence_score: float
    created_at: datetime


class MessageResponse(BaseModel):
    id: str
    campaign_id: str
    template_id: str | None
    recipient_profile_id: str | None
    subject: str
    body_text: str
    channel: str
    tone: str
    status: str
    generated_by_model: str | None
    token_count: int | None
    compliance_check_passed: bool
    created_at: datetime
    updated_at: datetime


class GenerateRequest(BaseModel):
    template_id: str | None = None
    tone: str | None = None
    motivation_reason: str = ""
    market_signals: list[str] = []


class DeliveryResponse(BaseModel):
    id: str
    message_id: str
    recipient_email: str
    channel: str
    status: str
    external_message_id: str | None
    attempt_count: int
    error_message: str | None
    sent_at: datetime | None
    delivered_at: datetime | None
    opened_at: datetime | None
    replied_at: datetime | None
    created_at: datetime


class DeliveryStatsResponse(BaseModel):
    total: int = 0
    pending: int = 0
    sent: int = 0
    delivered: int = 0
    bounced: int = 0
    opened: int = 0
    replied: int = 0
    failed: int = 0


class VariantCreate(BaseModel):
    variant_label: str
    subject: str
    body_text: str


class VariantResponse(BaseModel):
    id: str
    message_id: str
    variant_label: str
    subject: str
    body_text: str
    score: float | None
    is_winner: bool
    created_at: datetime
