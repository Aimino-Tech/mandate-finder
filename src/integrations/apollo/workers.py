import os
from taskiq import TaskiqState
from taskiq.events import TaskiqEvents
from taskiq_aio_pika import AioPikaBroker
from src.config import settings
from src.integrations.apollo.client import ApolloClient
from src.integrations.apollo.company_enricher import CompanyEnricher
from src.integrations.apollo.contact_finder import ContactFinder
from src.integrations.apollo.models import Contact, EnrichedCompany
from src.integrations.apollo.rate_limiter import TierRateLimiter

def _get_api_key(): return settings.apollo_api_key or os.environ.get("APOLLO_API_KEY", "")
def _get_tier(): return settings.apollo_tier or os.environ.get("APOLLO_TIER", "free")
def _get_amqp_url(): return os.environ.get("TASKIQ_AMQP_URL", "amqp://guest:guest@localhost:5672/")

class CompanyEnrichmentWorker:
    def __init__(self, api_key="", tier=""):
        limiter = TierRateLimiter(tier or _get_tier())
        client = ApolloClient(api_key=api_key or _get_api_key())
        self._enricher = CompanyEnricher(client=client, rate_limiter=limiter)
        self._finder = ContactFinder(client=client, rate_limiter=limiter)
    async def enrich_company(self, name, domain="", mock=False):
        return await self._enricher.enrich(name, domain, mock=mock)
    async def find_contacts(self, company_name, company_domain="", title_keywords=None, mock=False):
        return await self._finder.find(company_name, company_domain, title_keywords, mock=mock)
    async def full_pipeline(self, name, domain="", title_keywords=None, mock=False):
        contacts = await self.find_contacts(name, domain, title_keywords, mock=mock)
        return {"company": (await self.enrich_company(name, domain, mock=mock)).model_dump(), "contacts": [c.model_dump() for c in contacts], "contact_count": len(contacts)}

class ContactDiscoveryWorker:
    def __init__(self, api_key="", tier=""):
        self._finder = ContactFinder(client=ApolloClient(api_key=api_key or _get_api_key()), rate_limiter=TierRateLimiter(tier or _get_tier()))
    async def discover(self, company_name, company_domain="", title_keywords=None, mock=False):
        return await self._finder.find(company_name, company_domain, title_keywords, mock=mock)

broker = AioPikaBroker(_get_amqp_url())
async def on_startup(state: TaskiqState): state.enricher = CompanyEnrichmentWorker(); state.discoverer = ContactDiscoveryWorker()
broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, on_startup)

@broker.task
async def enrich_company_task(name, domain=""): return await CompanyEnrichmentWorker().enrich_company(name, domain)
@broker.task
async def find_contacts_task(company_name, company_domain="", title_keywords=None): return await ContactDiscoveryWorker().discover(company_name, company_domain, title_keywords)
