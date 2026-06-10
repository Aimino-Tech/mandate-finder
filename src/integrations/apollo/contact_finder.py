from typing import Any
from src.integrations.apollo.client import ApolloClient
from src.integrations.apollo.models import Contact
from src.integrations.apollo.rate_limiter import TierRateLimiter

class ContactFinder:
    def __init__(self, client=None, rate_limiter=None, api_key=""):
        self._client = client or ApolloClient(api_key=api_key)
        self._limiter = rate_limiter or TierRateLimiter("free")
    async def find(self, company_name, company_domain="", title_keywords=None, mock=False):
        if mock:
            return _mock_find(company_name, company_domain, title_keywords)
        async with self._limiter.throttle():
            people = await self._client.search_people(self._build_query(company_name, company_domain, title_keywords))
        return [_parse_contact(p, company_name, company_domain) for p in people]
    @staticmethod
    def _build_query(company_name, company_domain="", title_keywords=None):
        q = {"q_organization_name": company_name, "person_titles": title_keywords or [], "page": 1, "per_page": 25, "contact_email_status": "verified"}
        if company_domain:
            q["q_organization_domain"] = company_domain
        return q

def _parse_contact(person, company_name="", company_domain=""):
    return Contact(
        id=person.get("id"), first_name=person.get("first_name", ""), last_name=person.get("last_name", ""),
        name=f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
        title=person.get("title", ""), email=person.get("email", ""), phone=person.get("phone", ""),
        linkedin_url=person.get("linkedin_url", ""), confidence_score=_compute_confidence(person),
        company_name=company_name or person.get("organization_name", ""),
        company_domain=company_domain or person.get("organization_domain", ""), raw=person)

def _compute_confidence(person):
    score = 0.0
    if person.get("email"): score += 0.4
    if person.get("email_status") == "verified": score += 0.2
    if person.get("linkedin_url"): score += 0.15
    if person.get("phone"): score += 0.1
    if person.get("title"): score += 0.15
    return round(min(score, 1.0), 2)

def _mock_find(company_name, company_domain="", title_keywords=None):
    domain = company_domain or "siemens.com"
    mock_data = _MOCK_CONTACTS.get(domain, _MOCK_CONTACTS.get("siemens.com", []))
    if title_keywords:
        kl = [k.lower() for k in title_keywords]
        mock_data = [c for c in mock_data if any(kw in (c.get("title") or "").lower() for kw in kl)]
    return [_parse_contact(p, company_name, domain) for p in mock_data]

_MOCK_CONTACTS = {
    "siemens.com": [
        {"id": "mock_person_001", "first_name": "Anna", "last_name": "Schmidt", "title": "HR Director", "email": "anna.schmidt@siemens.com", "phone": "+49 89 123456", "linkedin_url": "https://linkedin.com/in/anna-schmidt", "email_status": "verified"},
        {"id": "mock_person_002", "first_name": "Max", "last_name": "Mueller", "title": "Talent Acquisition Lead", "email": "max.mueller@siemens.com", "phone": "", "linkedin_url": "https://linkedin.com/in/max-mueller", "email_status": "verified"},
        {"id": "mock_person_003", "first_name": "Julia", "last_name": "Weber", "title": "VP People & Culture", "email": "julia.weber@siemens.com", "phone": "+49 89 654321", "linkedin_url": "https://linkedin.com/in/julia-weber", "email_status": "verified"},
    ],
}
