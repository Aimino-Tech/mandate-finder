"""Hermes agent prompts for each German job board.

Each agent is configured with a system prompt that describes how to extract
job listing data from the HTML of the respective board. The prompts instruct
the Hermes model (LLM) to return structured JSON.

Usage:
    agent = HERMES_AGENTS["stepstone"]
    html = fetch_source(...)
    result = await agent.extract(html)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HermesAgentConfig:
    """Configuration for a Hermes scrap agent targeting one job board."""

    name: str
    display_name: str
    base_url: str
    system_prompt: str
    extraction_schema: dict[str, Any] = field(default_factory=dict)
    rate_limit_per_minute: int = 30
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def extraction_prompt(self) -> str:
        """Full prompt combining system instructions with schema requirements."""
        return f"{self.system_prompt}\n\nReturn a JSON array of objects with these fields:\n{self.extraction_schema}"


# -- Extraction schema shared across boards --
_EXTRACTION_SCHEMA = {
    "title": "string -- Job title",
    "company_name": "string -- Hiring company name",
    "location": "string -- Job location (city, region)",
    "description": "string -- Full job description text",
    "posted_date": "string -- Relative or absolute date (e.g. '3 days ago', '2026-06-01')",
    "application_url": "string -- Direct application or detail page URL",
    "salary": "string (optional) -- Salary range if visible",
    "job_type": "string (optional) -- e.g. 'full-time', 'part-time', 'remote'",
    "external_id": "string (optional) -- Board-specific job ID",
}


# -- Agent definitions --

STEPSTONE_AGENT = HermesAgentConfig(
    name="stepstone",
    display_name="StepStone.de",
    base_url="https://www.stepstone.de",
    system_prompt=(
        "You are a job listing extraction agent for StepStone.de. "
        "Parse the given HTML and extract all job listings on the page. "
        "StepStone listings contain job titles inside <h2> or <a> elements "
        "with class containing 'job-title', company names in elements with "
        "class containing 'company-name', and locations with class containing "
        "'location'. Descriptions are in 'job-description' elements. "
        "Posted dates are often shown as relative text like 'Heute' or 'Gestern' "
        "or in time elements. Application URLs are links to detail pages. "
        "Extract all available listings. Return results in German if the content is German."
    ),
    extraction_schema=_EXTRACTION_SCHEMA,
    rate_limit_per_minute=20,
    headers={
        "User-Agent": "Mozilla/5.0 (compatible; MandateFinderBot/1.0; +https://mandatefinder.ai)"
    },
)

XING_AGENT = HermesAgentConfig(
    name="xing",
    display_name="Xing Jobs",
    base_url="https://www.xing.com/jobs",
    system_prompt=(
        "You are a job listing extraction agent for Xing Jobs. "
        "Parse the given HTML and extract all job listings. "
        "Xing listings have job titles in heading elements with class 'job-title', "
        "company names in elements with class 'company-name' or 'tile-company-name', "
        "locations in 'tile-location' or 'job-location' elements. "
        "Descriptions are found in 'description' or 'job-description' sections. "
        "Posted dates appear relative ('vor 3 Tagen') or absolute. "
        "Application URLs point to the job detail page. "
        "Return results in German if the content is German."
    ),
    extraction_schema=_EXTRACTION_SCHEMA,
    rate_limit_per_minute=20,
)

INDEED_DE_AGENT = HermesAgentConfig(
    name="indeed_de",
    display_name="Indeed Deutschland",
    base_url="https://de.indeed.com",
    system_prompt=(
        "You are a job listing extraction agent for Indeed Germany (de.indeed.com). "
        "Parse the given HTML and extract all job listings. "
        "Indeed listings have job titles in <h2> elements with class 'jobTitle' or "
        "inside <a> elements with data-jk attributes. Company names are in elements "
        "with class 'companyName' or 'company_location'. Locations are in elements "
        "with class 'companyLocation'. Descriptions are in elements with class "
        "'job-snippet' or 'job-description'. Posted dates are in 'date' or 'postedDate' "
        "elements. Application URLs can be constructed from the job key. "
        "Return results in German where applicable."
    ),
    extraction_schema=_EXTRACTION_SCHEMA,
    rate_limit_per_minute=15,
)

LINKEDIN_AGENT = HermesAgentConfig(
    name="linkedin",
    display_name="LinkedIn Jobs",
    base_url="https://www.linkedin.com/jobs",
    system_prompt=(
        "You are a job listing extraction agent for LinkedIn Jobs. "
        "Parse the given HTML and extract all job listings. "
        "LinkedIn listings have job titles in <h3> or <a> elements with "
        "class containing 'job-title' or 'base-search-card__title'. "
        "Company names are in elements with class containing 'subtitle' or "
        "'job-search-card__subtitle'. Locations are in elements with class "
        "containing 'metadata' or 'job-search-card__location'. "
        "Descriptions require navigating to detail pages; use snippet text "
        "when available. Posted dates are in 'time' elements or as relative text. "
        "Application URLs are links to the job detail page."
    ),
    extraction_schema=_EXTRACTION_SCHEMA,
    rate_limit_per_minute=15,
)

KIMETA_AGENT = HermesAgentConfig(
    name="kimeta",
    display_name="Kimeta",
    base_url="https://www.kimeta.de",
    system_prompt=(
        "You are a job listing extraction agent for Kimeta.de. "
        "Parse the given HTML and extract all job listings. "
        "Kimeta listings have job titles in heading elements, company names "
        "in 'arbeitgeber' or company-name elements, locations in 'ort' elements. "
        "Descriptions are in description or snippet sections. "
        "Posted dates are often shown as relative text. "
        "Return results in German."
    ),
    extraction_schema=_EXTRACTION_SCHEMA,
    rate_limit_per_minute=25,
)

INTERAMT_AGENT = HermesAgentConfig(
    name="interamt",
    display_name="Interamt",
    base_url="https://www.interamt.de",
    system_prompt=(
        "You are a job listing extraction agent for Interamt.de (German public sector). "
        "Parse the given HTML and extract all job listings. "
        "Interamt listings have job titles in heading or link elements, "
        "organization names (employer) in 'stelle-arbeitgeber' or similar, "
        "locations in 'stelle-ort' or location elements. "
        "Descriptions are in detail or description sections. "
        "Posted dates appear as 'Veröffentlicht am' or similar. "
        "Return results in German."
    ),
    extraction_schema=_EXTRACTION_SCHEMA,
    rate_limit_per_minute=30,
)

MONSTER_DE_AGENT = HermesAgentConfig(
    name="monster_de",
    display_name="Monster Deutschland",
    base_url="https://www.monster.de",
    system_prompt=(
        "You are a job listing extraction agent for Monster Germany (monster.de). "
        "Parse the given HTML and extract all job listings. "
        "Monster listings have job titles in heading or link elements with "
        "class containing 'title', company names in elements with "
        "class containing 'company', locations in elements with "
        "class containing 'location'. Descriptions are in 'summary' or "
        "'description' sections. Posted dates are relative or in date elements. "
        "Return results in German where applicable."
    ),
    extraction_schema=_EXTRACTION_SCHEMA,
    rate_limit_per_minute=20,
)

# -- Registry --

HERMES_AGENTS: dict[str, HermesAgentConfig] = {
    "stepstone": STEPSTONE_AGENT,
    "xing": XING_AGENT,
    "indeed_de": INDEED_DE_AGENT,
    "linkedin": LINKEDIN_AGENT,
    "kimeta": KIMETA_AGENT,
    "interamt": INTERAMT_AGENT,
    "monster_de": MONSTER_DE_AGENT,
}
