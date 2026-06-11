import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SearchProfileCreate(BaseModel):
    user_id: uuid.UUID
    name: str = Field(max_length=255)
    keywords: str
    location: str | None = None
    radius_km: int | None = None
    industries: list[str] | None = None
    salary_min: float | None = None
    employment_type: str | None = None
    exclusions: list[str] | None = None
    notify_on_score_above: float = 0.8
    notify_channels: str = "email"


class SearchProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    keywords: str | None = None
    location: str | None = None
    radius_km: int | None = None
    industries: list[str] | None = None
    salary_min: float | None = None
    employment_type: str | None = None
    exclusions: list[str] | None = None
    is_active: bool | None = None
    notify_on_score_above: float | None = None
    notify_channels: str | None = None


class SearchProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    keywords: str
    location: str | None
    radius_km: int | None
    industries: str | None
    salary_min: float | None
    employment_type: str | None
    exclusions: str | None
    is_active: bool
    notify_on_score_above: float
    notify_channels: str
    created_at: datetime
    last_run_at: datetime | None

    model_config = {"from_attributes": True}
