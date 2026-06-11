from src.integrations.apollo.client import ApolloClient
from src.integrations.apollo.models import EnrichedCompany
from src.integrations.apollo.rate_limiter import TierRateLimiter


class CompanyEnricher:
    def __init__(self, client=None, rate_limiter=None, api_key=""):
        self._client = client or ApolloClient(api_key=api_key)
        self._limiter = rate_limiter or TierRateLimiter("free")
    async def enrich(self, name, domain="", mock=False):
        if mock:
            return _mock_enrich(name, domain)
        async with self._limiter.throttle():
            org = await self._client.match_organization(domain=domain, name=name)
        if not org or org.get("id") is None:
            async with self._limiter.throttle():
                results = await self._client.search_organizations({"q": name, "per_page": 5})
            org = results[0] if results else {}
        return _parse_organization(org)
    async def batch_enrich(self, companies, mock=False):
        return [await self.enrich(n, d, mock=mock) for n, d in companies]

def _parse_organization(org):
    return EnrichedCompany(
        id=org.get("id"), name=org.get("name", ""), domain=org.get("domain", ""),
        industry=org.get("industry", ""),
        employees=org.get("employee_count", 0) or org.get("estimated_num_employees", 0) or 0,
        revenue_range=org.get("revenue_range", ""), total_funding=org.get("total_funding", ""),
        founded_year=org.get("founded_year"),
        description=org.get("short_description", "") or org.get("long_description", ""),
        linkedin_url=org.get("linkedin_url", ""), logo_url=org.get("logo_url", ""), raw=org)

def _mock_enrich(name, domain=""):
    data = _MOCK_ORGANIZATIONS.get(domain) or _MOCK_ORGANIZATIONS.get(name.lower(), {})
    return EnrichedCompany(**{**{"name": name, "domain": domain}, **data, "raw": data})

_MOCK_ORGANIZATIONS = {
    "siemens.com": {"id": "mock_org_001", "name": "Siemens", "domain": "siemens.com", "industry": "Industrial", "employees": 320000, "revenue_range": "€50B+", "total_funding": "", "founded_year": 1847, "description": "Siemens is a technology company focused on industry, infrastructure, and transport.", "linkedin_url": "https://linkedin.com/company/siemens", "logo_url": "https://logo.clearbit.com/siemens.com"},
    "siemens": {"id": "mock_org_001", "name": "Siemens", "domain": "siemens.com", "industry": "Industrial", "employees": 320000, "revenue_range": "€50B+", "total_funding": "", "founded_year": 1847, "description": "Siemens is a technology company focused on industry, infrastructure, and transport.", "linkedin_url": "https://linkedin.com/company/siemens", "logo_url": "https://logo.clearbit.com/siemens.com"},
}
