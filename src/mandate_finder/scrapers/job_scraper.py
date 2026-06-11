"""Job scraper orchestration -- maps source names to Hermes agents.

Provides the JobScraperRegistry and the primary `scrape_source` entrypoint
that invokes a Hermes agent for a given source and normalizes results.
"""

from __future__ import annotations

import logging
from typing import Any

from mandate_finder.scrapers.hermes_agents import HERMES_AGENTS, HermesAgentConfig
from mandate_finder.schemas.scraping import RawJobData

logger = logging.getLogger(__name__)


class JobScraperRegistry:
    """Maps source names to their Hermes agent configuration."""

    _agents: dict[str, HermesAgentConfig] = {}

    @classmethod
    def register(cls, agent: HermesAgentConfig) -> None:
        cls._agents[agent.name] = agent

    @classmethod
    def get(cls, name: str) -> HermesAgentConfig | None:
        return cls._agents.get(name)

    @classmethod
    def all(cls) -> dict[str, HermesAgentConfig]:
        return dict(cls._agents)

    @classmethod
    def active_names(cls) -> list[str]:
        return list(cls._agents.keys())


# Pre-register all known agents
for _agent in HERMES_AGENTS.values():
    JobScraperRegistry.register(_agent)


async def scrape_source(
    source: str | HermesAgentConfig,
    search_terms: list[str] | None = None,
) -> list[RawJobData]:
    """Scrape a job board source using its Hermes agent.

    Args:
        source: Source name (str) or HermesAgentConfig object.
        search_terms: Optional search terms to narrow the scrape.

    Returns:
        A list of normalized RawJobData objects.

    Raises:
        ValueError: If the source name is unknown.
    """
    if isinstance(source, str):
        config = JobScraperRegistry.get(source)
        if config is None:
            raise ValueError(
                f"Unknown scrap source: {source!r}. "
                f"Known: {JobScraperRegistry.active_names()}"
            )
    elif isinstance(source, HermesAgentConfig):
        config = source
    else:
        raise TypeError(f"Expected str or HermesAgentConfig, got {type(source).__name__}")

    search_url = _build_search_url(config, search_terms)
    logger.info("Scraping %s via Hermes agent (url=%s)", config.name, search_url)

    raw_listings: list[dict[str, Any]] = await _invoke_hermes_agent(config, search_url)

    results = []
    for item in raw_listings:
        try:
            job = _normalize(item, source_name=config.name, board_url=config.base_url)
            results.append(job)
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed listing from %s: %s", config.name, exc)
            continue

    logger.info("Scrape complete for %s: %d jobs found", config.name, len(results))
    return results


def _build_search_url(config: HermesAgentConfig, search_terms: list[str] | None) -> str:
    """Build a search URL appropriate for the job board."""
    if not search_terms:
        return config.base_url

    query = "+".join(search_terms)
    url_patterns = {
        "stepstone": f"{config.base_url}/5/ergebnisse.html?keywords={query}",
        "xing": f"{config.base_url}/jobs?query={query}",
        "indeed_de": f"https://de.indeed.com/jobs?q={query}",
        "linkedin": f"{config.base_url}/search?keywords={query}",
        "kimeta": f"{config.base_url}/stellenanzeigen?q={query}",
        "interamt": f"{config.base_url}/stellenangebote?suche={query}",
        "monster_de": f"https://www.monster.de/jobs/suche?q={query}",
    }
    return url_patterns.get(config.name, f"{config.base_url}/search?q={query}")


async def _invoke_hermes_agent(
    config: HermesAgentConfig, url: str
) -> list[dict[str, Any]]:
    """Invoke the Hermes LLM agent to extract job listings.

    In production this calls the external Hermes API. Here we return
    an empty list as a stub -- the actual integration is injected via
    the worker or a separate Hermes client module.
    """
    # TODO: Replace with actual Hermes API call
    logger.debug("Hermes agent stub invoked for %s (url=%s)", config.name, url)
    return []


def _normalize(
    item: dict[str, Any],
    source_name: str,
    board_url: str,
) -> RawJobData:
    """Normalize a raw extracted dict to our RawJobData schema."""
    title = (item.get("title") or "").strip()
    company = (item.get("company_name") or item.get("company") or "").strip()
    location = (item.get("location") or "").strip()
    description = (item.get("description") or "").strip()
    application_url = (item.get("application_url") or item.get("url") or "").strip()
    posted_date = (item.get("posted_date") or "").strip() or None
    external_id = (item.get("external_id") or "").strip() or None
    salary = (item.get("salary") or "").strip() or None
    job_type = (item.get("job_type") or "").strip() or None

    if not title:
        raise ValueError("Missing required field: title")
    if not company:
        raise ValueError("Missing required field: company_name")
    if not location:
        raise ValueError("Missing required field: location")

    if not external_id:
        external_id = f"{source_name}::{title}::{company}::{location}"

    return RawJobData(
        title=title,
        company_name=company,
        location=location,
        description=description or "No description available.",
        source_url=application_url or f"{board_url}/job/{external_id}",
        posted_date=posted_date,
        source=source_name,
        external_id=external_id,
        salary=salary,
        job_type=job_type,
    )
