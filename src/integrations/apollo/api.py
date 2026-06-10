from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Query

from src.integrations.apollo.company_enricher import CompanyEnricher
from src.integrations.apollo.contact_finder import ContactFinder
from src.integrations.apollo.models import (
    Contact,
    ContactSearchRequest,
    EnrichedCompany,
    EnrichmentRequest,
    EnrichmentResult,
)

router = APIRouter(prefix="/api/enrichment", tags=["enrichment"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "apollo-enrichment", "version": "0.1.0"}


@router.post("/company", response_model=EnrichedCompany)
async def enrich_company(
    request: Annotated[EnrichmentRequest, Body()],
    mock: bool = Query(default=False),
) -> EnrichedCompany:
    enricher = CompanyEnricher()
    return await enricher.enrich(name=request.company_name, domain=request.domain, mock=mock)


@router.post("/contacts", response_model=list[Contact])
async def find_contacts(
    request: Annotated[ContactSearchRequest, Body()],
    mock: bool = Query(default=False),
) -> list[Contact]:
    finder = ContactFinder()
    return await finder.find(
        company_name=request.company_name,
        company_domain=request.company_domain,
        title_keywords=request.title_keywords,
        mock=mock,
    )


@router.post("/enrich", response_model=EnrichmentResult)
async def enrich_company_with_contacts(
    request: Annotated[EnrichmentRequest, Body()],
    title_keywords: list[str] = Body(default=["HR", "Talent", "Recruiting", "People"]),
    limit: int = Body(default=10, ge=1, le=50),
    mock: bool = Query(default=False),
) -> EnrichmentResult:
    enricher = CompanyEnricher()
    company = await enricher.enrich(name=request.company_name, domain=request.domain, mock=mock)
    finder = ContactFinder()
    contacts = await finder.find(
        company_name=request.company_name,
        company_domain=request.domain,
        title_keywords=title_keywords,
        mock=mock,
    )
    return EnrichmentResult(company=company, contacts=contacts[:limit])
