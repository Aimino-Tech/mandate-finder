from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CompanySignalResponse(BaseModel):
    id: UUID
    company_id: UUID
    company_name: str
    competitor_count: int
    trend: str
    last_updated: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanySignalTimeline(BaseModel):
    date: datetime
    competitor_count: int


class CompanyInsightResponse(BaseModel):
    company_id: UUID
    company_name: str
    competitor_count: int
    trend: str
    timeline: list[CompanySignalTimeline]


class HeatmapItem(BaseModel):
    company_id: UUID
    company_name: str
    competitor_count: int
    trend: str


class HeatmapResponse(BaseModel):
    items: list[HeatmapItem]


class AlternativeRecommendation(BaseModel):
    company_id: UUID
    company_name: str
    competitor_count: int
    rationale: str


class WatchlistCreate(BaseModel):
    company_id: UUID
    company_name: str
    notify_on_change: bool = True


class WatchlistResponse(BaseModel):
    id: UUID
    company_id: UUID
    company_name: str
    notify_on_change: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivityEventCreate(BaseModel):
    company_id: UUID
    activity_type: str  # outreach, applied, viewed
    is_private: bool = False


class InsightReport(BaseModel):
    generated_at: datetime
    company_signals: list[CompanySignalResponse]
    watchlist: list[WatchlistResponse]
    alternatives: list[AlternativeRecommendation]
