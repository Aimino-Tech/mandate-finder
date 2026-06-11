"""Tests for Bundesagentur für Arbeit integration.

Parser and client tests are synchronous (no DB needed).
DB-dependent tests are skipped if PostgreSQL is unavailable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from mandate_finder.integrations.bundesagentur.client import (
    BundesagenturClient,
    BundesagenturAuthError,
    BundesagenturRateLimitError,
)
from mandate_finder.integrations.bundesagentur.parser import parse_job_response

# Path to test fixtures directory (relative to this file)
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ─── Fixtures (sync) ────────────────────────────────────────────────

@pytest.fixture
def ba_sample_response_xml() -> bytes:
    """Read the BA sample XML response fixture."""
    return (_FIXTURES_DIR / "ba_jobs_response.xml").read_bytes()


@pytest.fixture
def ba_sample_response_json() -> dict[str, Any]:
    """Sample JSON response matching BA API v4 format."""
    return {
        "list": [
            {
                "beruf": {
                    "refnr": "BA-100001-ABCD",
                    "titel": "Senior React Entwickler",
                    "arbeitgeber": "TechCorp GmbH",
                    "ort": {"ort": "Berlin", "region": "Berlin"},
                    "beschreibung": "Wir suchen einen erfahrenen Senior React Entwickler.",
                    "berufscode": "43103",
                    "art": "1",
                    "aktuelleVeroeffentlichungsdatum": "2026-06-10T08:00:00",
                    "link": "https://example.com/jobs/BA-100001-ABCD",
                    "vergutung": {
                        "minValue": "65000",
                        "maxValue": "95000",
                        "currency": "EUR",
                    },
                }
            },
            {
                "beruf": {
                    "refnr": "BA-100002-EFGH",
                    "titel": "Full Stack Developer (React/Python)",
                    "arbeitgeber": "DigitalSolutions AG",
                    "ort": {"ort": "München", "region": "Bayern"},
                    "beschreibung": "Full Stack Developer gesucht.",
                    "berufscode": "43102",
                    "art": "1",
                    "aktuelleVeroeffentlichungsdatum": "2026-06-09T10:30:00",
                    "link": "https://example.com/jobs/BA-100002-EFGH",
                    "vergutung": {
                        "minValue": "55000",
                        "maxValue": "85000",
                        "currency": "EUR",
                    },
                }
            },
        ]
    }


# ─── Parser Tests (sync, no DB) ─────────────────────────────────────

class TestBundesagenturParser:
    """Test the BA API response parser (no database required)."""

    def test_parse_xml_response(self, ba_sample_response_xml: bytes) -> None:
        """Test parsing XML BA response into normalized job records."""
        jobs = parse_job_response(ba_sample_response_xml)
        assert len(jobs) == 5

        first = jobs[0]
        assert first["source_job_id"] == "BA-100001-ABCD"
        assert first["title"] == "Senior React Entwickler"
        assert first["company_name"] == "TechCorp GmbH"
        assert first["location_city"] == "Berlin"
        assert first["location_state"] == "Berlin"
        assert first["occupation_code"] == "43103"
        assert first["posted_at"] is not None
        assert first["source_url"] == "https://example.com/jobs/BA-100001-ABCD"

    def test_parse_json_response(self, ba_sample_response_json: dict[str, Any]) -> None:
        """Test parsing JSON BA response into normalized job records."""
        jobs = parse_job_response(ba_sample_response_json)
        assert len(jobs) == 2

        first = jobs[0]
        assert first["source_job_id"] == "BA-100001-ABCD"
        assert first["title"] == "Senior React Entwickler"
        assert first["company_name"] == "TechCorp GmbH"
        assert first["location_city"] == "Berlin"
        assert first["location_state"] == "Berlin"
        assert first["occupation_code"] == "43103"
        assert first["employment_type"] == "full_time"
        assert first["posted_at"] is not None
        assert first["salary_min"] == 65000.0
        assert first["salary_max"] == 95000.0
        assert first["salary_currency"] == "EUR"
        assert first["source_url"] == "https://example.com/jobs/BA-100001-ABCD"

    def test_parse_empty_response(self) -> None:
        """Test parsing an empty response returns empty list."""
        assert parse_job_response({}) == []
        assert parse_job_response({"list": []}) == []

    def test_parse_malformed_fields(self) -> None:
        """Test parsing gracefully handles missing/malformed fields."""
        data = {
            "list": [
                {"beruf": {"titel": "Test Job"}},
                {"beruf": {}},
            ]
        }
        jobs = parse_job_response(data)
        assert len(jobs) == 2
        assert jobs[0]["title"] == "Test Job"
        assert jobs[0]["company_name"] == ""
        assert jobs[1]["title"] == ""


# ─── Client Tests (mocked HTTP) ─────────────────────────────────────

class TestBundesagenturClient:
    """Test the BA API client (mocked HTTP, no database required)."""

    def test_health_check_unconfigured(self) -> None:
        """Health check returns False when API key is missing."""
        import asyncio
        c = BundesagenturClient(api_key="")
        health = asyncio.run(c.health_check())
        assert health is False

    def test_auth_error_handling(self) -> None:
        """Auth errors are properly wrapped."""
        import asyncio
        c = BundesagenturClient(api_key="bad-key")
        with patch.object(c, "_authenticate", side_effect=BundesagenturAuthError("mock")):
            with pytest.raises(BundesagenturAuthError):
                asyncio.run(c.search_jobs("test"))

    def test_rate_limit_error_handling(self) -> None:
        """429 responses raise RateLimitError."""
        import asyncio

        async def mock_request(*args, **kwargs):
            raise BundesagenturRateLimitError("BA API rate limit exceeded")

        c = BundesagenturClient(api_key="test-key")
        with patch.object(c, "_request", mock_request):
            with pytest.raises(BundesagenturRateLimitError):
                asyncio.run(c.search_jobs("test"))


# ─── Relevance Matching Test (sync, no DB) ──────────────────────────

class TestBundesagenturRelevance:
    """Test relevance matching of parsed BA jobs (no database required)."""

    def test_relevance_matching(self, ba_sample_response_xml: bytes) -> None:
        """Test that parsed BA jobs can be matched against a search profile."""
        from mandate_finder.integrations.bundesagentur.parser import parse_job_response

        jobs = parse_job_response(ba_sample_response_xml)
        assert len(jobs) > 0

        keywords = ["senior", "react", "entwickler"]
        location = "Berlin"

        matches = []
        for job in jobs:
            score = 0.0
            reasoning_parts = []

            title_lower = job["title"].lower()
            desc_lower = (job.get("description") or "").lower()
            text = f"{title_lower} {desc_lower}"

            for kw in keywords:
                if kw.lower() in text:
                    score += 0.25
                    reasoning_parts.append(f"Keyword '{kw}' found")

            if location.lower() in (job.get("location_city") or "").lower():
                score += 0.15
                reasoning_parts.append(f"Location matches '{location}'")

            if score > 0.5:
                matches.append({
                    "score": round(score, 2),
                    "reasoning": "; ".join(reasoning_parts) if reasoning_parts else "No specific reasoning",
                    "job": job,
                })

        assert len(matches) > 0
        assert matches[0]["score"] > 0.5
        assert matches[0]["reasoning"] != ""


# ─── DB-dependent Tests (skipped if PostgreSQL unavailable) ─────────

# Check DB availability once at module level
_HAS_DB = False
try:
    import asyncpg
    import asyncio

    async def _check_db():
        try:
            conn = await asyncpg.connect(
                user="mandate", password="mandate", database="mandate_finder",
                host="127.0.0.1", port=5432, timeout=2,
            )
            await conn.close()
            return True
        except Exception:
            return False

    _HAS_DB = asyncio.run(_check_db())
except ImportError:
    pass


db_required = pytest.mark.skipif(not _HAS_DB, reason="PostgreSQL test database not available")


@db_required
@pytest.mark.asyncio
async def test_ba_job_ingestion(
    ba_sample_response_xml: bytes,
    db_session,  # type: ignore[arg-type]
) -> None:
    """End-to-end test: parse BA response and store jobs (requires DB)."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from mandate_finder.models.job_posting import JobPosting

    jobs = parse_job_response(ba_sample_response_xml)
    assert len(jobs) > 0

    for record in jobs:
        job = JobPosting(
            source="bundesagentur",
            source_job_id=record["source_job_id"],
            title=record["title"],
            company_name=record["company_name"],
            location_city=record.get("location_city"),
            location_state=record.get("location_state"),
            description=record.get("description"),
            occupation_code=record.get("occupation_code"),
            salary_min=record.get("salary_min"),
            salary_max=record.get("salary_max"),
            salary_currency=record.get("salary_currency"),
            employment_type=record.get("employment_type"),
            posted_at=record.get("posted_at"),
            source_url=record.get("source_url"),
            raw_data=record.get("raw_data"),
        )
        db_session.add(job)

    await db_session.commit()

    result = await db_session.execute(select(JobPosting))
    stored = result.scalars().all()
    assert len(stored) == 5

    result = await db_session.execute(
        select(JobPosting).where(JobPosting.source_job_id == "BA-100001-ABCD")
    )
    job = result.scalar_one_or_none()
    assert job is not None
    assert job.title == "Senior React Entwickler"
    assert job.company_name == "TechCorp GmbH"
    assert job.source == "bundesagentur"


@db_required
@pytest.mark.asyncio
async def test_ba_api_routes(async_client) -> None:  # type: ignore[arg-type]
    """Test the BA integration API endpoints (requires DB)."""
    resp = await async_client.get("/api/v1/integrations/ba/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data
    assert "total_jobs" in data
    assert "sources" in data

    resp = await async_client.post(
        "/api/v1/integrations/ba/search",
        json={"keywords": "React", "location": "Berlin", "page": 1},
    )
    if resp.status_code != 200:
        assert resp.status_code == 503  # Not configured

    resp = await async_client.post(
        "/api/v1/integrations/ba/ingest",
        json={"keywords": "Software Engineer", "location": "Berlin", "max_pages": 1},
    )
    if resp.status_code != 200:
        assert resp.status_code == 503  # Not configured
