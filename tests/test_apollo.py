import pytest
from src.integrations.apollo.company_enricher import CompanyEnricher
from src.integrations.apollo.contact_finder import ContactFinder
from src.integrations.apollo.models import Contact, EnrichedCompany
from src.integrations.apollo.rate_limiter import TierRateLimiter

@pytest.mark.asyncio
async def test_company_enricher_mock():
    r = await CompanyEnricher(api_key="mock_key").enrich(name="Siemens", domain="siemens.com", mock=True)
    assert isinstance(r, EnrichedCompany) and r.name == "Siemens" and r.industry == "Industrial" and r.employees > 10000

@pytest.mark.asyncio
async def test_company_enricher_no_mock_without_key():
    assert (await CompanyEnricher().enrich(name="Siemens", domain="siemens.com")).id is None

@pytest.mark.asyncio
async def test_contact_finder_mock_hr_keywords():
    c = await ContactFinder(api_key="mock_key").find(company_name="Siemens", company_domain="siemens.com", title_keywords=["HR", "Talent"], mock=True)
    assert len(c) > 0 and all(isinstance(x, Contact) for x in c) and all(x.confidence_score > 0.5 for x in c)

@pytest.mark.asyncio
async def test_contact_finder_confidence_scoring():
    c = await ContactFinder(api_key="mock_key").find(company_name="Siemens", mock=True)
    assert len(c) == 3 and all(0.0 <= x.confidence_score <= 1.0 for x in c)

@pytest.mark.asyncio
async def test_contact_finder_no_mock_without_key():
    assert await ContactFinder().find(company_name="Siemens") == []

@pytest.mark.asyncio
async def test_company_to_decision_maker_flow():
    e = await CompanyEnricher(api_key="mock_key").enrich(name="Siemens", domain="siemens.com", mock=True)
    assert e.industry == "Industrial" and e.employees > 10000
    c = await ContactFinder(api_key="mock_key").find(company_name=e.name, company_domain=e.domain, title_keywords=["HR", "Talent"], mock=True)
    assert len(c) > 0 and "@siemens.com" in c[0].email and c[0].confidence_score > 0.5

def test_tier_rate_limiter_default(): assert TierRateLimiter("free").tier == "free"
def test_tier_rate_limiter_pro(): assert TierRateLimiter("pro").tier == "pro"
def test_tier_rate_limiter_unknown_falls_back_to_free():
    l = TierRateLimiter("unknown"); assert l.tier == "unknown" and l._limiter.rate == 100 / 86400.0

@pytest.mark.asyncio
async def test_company_enrichment_worker_enrich():
    from src.integrations.apollo.workers import CompanyEnrichmentWorker
    r = await CompanyEnrichmentWorker(api_key="mock_key", tier="free").enrich_company("Siemens", "siemens.com", mock=True)
    assert isinstance(r, EnrichedCompany) and r.industry == "Industrial"

@pytest.mark.asyncio
async def test_contact_discovery_worker_discover():
    from src.integrations.apollo.workers import ContactDiscoveryWorker
    c = await ContactDiscoveryWorker(api_key="mock_key", tier="free").discover("Siemens", "siemens.com", ["HR"], mock=True)
    assert len(c) > 0 and c[0].confidence_score > 0.5

@pytest.mark.asyncio
async def test_company_enrichment_worker_pipeline():
    from src.integrations.apollo.workers import CompanyEnrichmentWorker
    r = await CompanyEnrichmentWorker(api_key="mock_key", tier="free").full_pipeline("Siemens", "siemens.com", ["HR", "Talent"], mock=True)
    assert "company" in r and "contacts" in r and r["contact_count"] > 0
