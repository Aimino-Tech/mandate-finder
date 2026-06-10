from typing import Any
from fastapi import APIRouter, HTTPException
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_502_BAD_GATEWAY
from src.config import settings
from src.integrations.apollo.client import ApolloClient
from src.integrations.apollo.company_enricher import CompanyEnricher
from src.integrations.apollo.contact_finder import ContactFinder
from src.integrations.apollo.models import Contact, EnrichedCompany
from src.integrations.apollo.rate_limiter import TierRateLimiter

router = APIRouter(prefix="/enrichment", tags=["enrichment"])

def _get_enricher(): return CompanyEnricher(api_key=settings.apollo_api_key, rate_limiter=TierRateLimiter(settings.apollo_tier or "free"))
def _get_finder(): return ContactFinder(api_key=settings.apollo_api_key, rate_limiter=TierRateLimiter(settings.apollo_tier or "free"))

@router.post("/company", response_model=EnrichedCompany)
async def enrich_company(name: str, domain: str = "", mock: bool = False):
    result = await _get_enricher().enrich(name=name, domain=domain, mock=mock)
    if result.id is None and not mock:
        raise HTTPException(status_code=HTTP_502_BAD_GATEWAY, detail="Failed to enrich company")
    return result

@router.post("/contacts", response_model=list[Contact])
async def find_contacts(company_name: str, company_domain: str = "", title_keywords: list[str] | None = None, mock: bool = False):
    return await _get_finder().find(company_name=company_name, company_domain=company_domain, title_keywords=title_keywords, mock=mock)

@router.post("/pipeline")
async def full_pipeline(name: str, domain: str = "", title_keywords: list[str] | None = None, mock: bool = False):
    enricher = _get_enricher(); finder = _get_finder()
    company = await enricher.enrich(name=name, domain=domain, mock=mock)
    contacts = await finder.find(company_name=name, company_domain=domain, title_keywords=title_keywords, mock=mock)
    return {"company": company.model_dump(), "contacts": [c.model_dump() for c in contacts], "contact_count": len(contacts)}

@router.post("/verify-email")
async def verify_email(email: str):
    if not email or "@" not in email:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid email address")
    result = await ApolloClient(api_key=settings.apollo_api_key).verify_email(email)
    if "error" in result and not settings.apollo_api_key:
        return {"email": email, "status": "unknown", "detail": "Apollo not configured"}
    return {"email": email, "status": result.get("status", "unknown"), "verified": result.get("status") == "valid"}
