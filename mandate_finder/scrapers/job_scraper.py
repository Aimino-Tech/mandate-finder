from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from mandate_finder.scrapers.hermes_agents import HERMES_AGENTS, HermesAgentConfig


class JobPosting(BaseModel):
    title: str
    company_name: str
    location: str
    description: str
    posted_date: str | None = None
    application_url: str | None = None
    source: str = "scrap"
    source_url: str | None = None
    scraped_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    fingerprint: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.fingerprint is None:
            self.fingerprint = dedup_key(self)


def dedup_key(posting: JobPosting) -> str:
    raw = "|".join(
        [
            _normalize(posting.company_name),
            _normalize(posting.title),
            _normalize(posting.location),
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9äöüß\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


class SourceHealth(BaseModel):
    source: str
    status: str  # "up" | "down"
    response_time_ms: float | None = None
    error: str | None = None
    jobs_found: int = 0
    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class JobScraperRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, HermesAgentConfig] = dict(HERMES_AGENTS)

    def register(self, source: str, config: HermesAgentConfig) -> None:
        self._agents[source] = config

    def get(self, source: str) -> HermesAgentConfig | None:
        return self._agents.get(source)

    def list_sources(self) -> list[str]:
        return list(self._agents.keys())

    def unregister(self, source: str) -> None:
        self._agents.pop(source, None)


async def scrape_source(
    source: str,
    html: str,
    registry: JobScraperRegistry | None = None,
) -> list[JobPosting]:
    if registry is None:
        registry = JobScraperRegistry()

    config = registry.get(source)
    if config is None:
        raise ValueError(f"Unknown source: {source}")

    import time

    start = time.monotonic()

    try:
        raw_jobs = await _call_hermes_agent(config, html)
    except Exception as exc:
        raise RuntimeError(f"Hermes agent failed for source '{source}'") from exc

    elapsed = (time.monotonic() - start) * 1000

    postings = []
    for raw in raw_jobs:
        posting = JobPosting(
            title=raw.get("title", ""),
            company_name=raw.get("company_name", ""),
            location=raw.get("location", ""),
            description=raw.get("description", ""),
            posted_date=raw.get("posted_date"),
            application_url=raw.get("application_url"),
            source=source,
            source_url=raw.get("application_url"),
        )
        postings.append(posting)

    return postings


async def _call_hermes_agent(
    config: HermesAgentConfig, html: str
) -> list[dict[str, Any]]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()

    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": config.system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Extract jobs from this HTML:\n\n{html[:50_000]}",
                    }
                ],
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    content = resp.choices[0].message.content or "{}"
    import json

    data = json.loads(content)

    if isinstance(data, dict):
        jobs = data.get("jobs", data.get("postings", []))
        if isinstance(jobs, dict):
            jobs = list(jobs.values())
    elif isinstance(data, list):
        jobs = data
    else:
        jobs = []

    return jobs
