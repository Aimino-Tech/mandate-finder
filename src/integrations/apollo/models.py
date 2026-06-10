from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EnrichedCompany(BaseModel):
    id: str | None = None
    name: str = ""
    domain: str = ""
    industry: str = ""
    employees: int = 0
    revenue_range: str = ""
    total_funding: str = ""
    founded_year: int | None = None
    description: str = ""
    linkedin_url: str = ""
    logo_url: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class Contact(BaseModel):
    id: str | None = None
    first_name: str = ""
    last_name: str = ""
    name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    confidence_score: float = 0.0
    company_name: str = ""
    company_domain: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class EnrichmentRequest(BaseModel):
    company_name: str
    domain: str = ""


class ContactSearchRequest(BaseModel):
    company_name: str
    company_domain: str = ""
    title_keywords: list[str] = Field(default_factory=lambda: ["HR", "Talent", "Recruiting", "People"])
    limit: int = Field(default=10, ge=1, le=50)
    min_confidence: float = Field(default=0.0, ge=0, le=1)


class EnrichmentResult(BaseModel):
    company: EnrichedCompany
    contacts: list[Contact] = Field(default_factory=list)


class ApolloRateLimit(BaseModel):
    daily_remaining: int = 0
    monthly_remaining: int = 0
    daily_limit: int = 100
    monthly_limit: int = 1000
