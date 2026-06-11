from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
from taskiq import TaskiqDepends

from mandate_finder.scrapers.job_scraper import (
    JobPosting,
    JobScraperRegistry,
    SourceHealth,
    scrape_source,
    dedup_key,
)


@dataclass
class ScrapeResult:
    postings: list[JobPosting] = field(default_factory=list)
    health: SourceHealth | None = None
    source: str = ""


class JobScrapingWorker:
    def __init__(
        self,
        registry: JobScraperRegistry | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.registry = registry or JobScraperRegistry()
        self.http = http_client or httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MandateFinder/1.0)"
            },
        )
        self._seen_fingerprints: set[str] = set()

    async def scrape_all(
        self,
        search_terms: str,
        sources: list[str] | None = None,
    ) -> AsyncIterator[ScrapeResult]:
        targets = sources or self.registry.list_sources()

        async with asyncio.TaskGroup() as tg:
            tasks = {
                src: tg.create_task(self._scrape_one(src, search_terms))
                for src in targets
            }

        for src in targets:
            result = tasks[src].result()
            yield result

    async def _scrape_one(
        self, source: str, search_terms: str
    ) -> ScrapeResult:
        start = time.monotonic()
        try:
            config = self.registry.get(source)
            if config is None:
                return ScrapeResult(
                    source=source,
                    health=SourceHealth(
                        source=source,
                        status="down",
                        error=f"Unknown source: {source}",
                    ),
                )

            url = f"{config.base_url}/jobs?q={search_terms}"
            resp = await self.http.get(url)
            resp.raise_for_status()
            elapsed = (time.monotonic() - start) * 1000

            raw_jobs = await scrape_source(source, resp.text, self.registry)

            postings = []
            for job in raw_jobs:
                fprint = job.fingerprint or dedup_key(job)
                if fprint in self._seen_fingerprints:
                    continue
                self._seen_fingerprints.add(fprint)
                postings.append(job)

            return ScrapeResult(
                source=source,
                postings=postings,
                health=SourceHealth(
                    source=source,
                    status="up",
                    response_time_ms=elapsed,
                    jobs_found=len(postings),
                ),
            )

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return ScrapeResult(
                source=source,
                health=SourceHealth(
                    source=source,
                    status="down",
                    response_time_ms=elapsed,
                    error=str(exc),
                ),
            )

    async def close(self) -> None:
        await self.http.aclose()


@JobScrapingWorker  # noqa: F811
async def run_job_scrape(
    search_terms: str,
    sources: list[str] | None = None,
    depends: TaskiqDepends = TaskiqDepends(),  # noqa: ARG001
) -> list[dict]:
    worker = JobScrapingWorker()
    results: list[dict] = []
    async for result in worker.scrape_all(search_terms, sources):
        results.append(
            {
                "source": result.source,
                "jobs": [j.model_dump() for j in result.postings],
                "health": result.health.model_dump() if result.health else None,
            }
        )
    await worker.close()
    return results
