from pathlib import Path

import pytest

from mandate_finder.integrations.bundesagentur.client import BundesagenturClient


@pytest.fixture
def ba_sample_response() -> bytes:
    return Path("tests/fixtures/ba_jobs_response.xml").read_bytes()


def test_parse_ba_response(ba_sample_response: bytes) -> None:
    xml = ba_sample_response.decode("utf-8")
    jobs = BundesagenturClient.parse_job_response(xml)

    assert len(jobs) == 3

    job = jobs[0]
    assert job["ba_job_id"] == "BA-12345"
    assert job["title"] == "Senior React Entwickler"
    assert job["company_name"] == "TechCorp GmbH"
    assert job["location_city"] == "Berlin"
    assert job["location_state"] == "Berlin"
    assert job["employment_type"] == "full_time"
    assert job["source_url"] == "https://example.com/apply/BA-12345"
    assert job["description"] is not None
    assert job["posted_at"] is not None
    assert job["last_modified"] is not None


def test_parse_part_time_job(ba_sample_response: bytes) -> None:
    xml = ba_sample_response.decode("utf-8")
    jobs = BundesagenturClient.parse_job_response(xml)

    job = jobs[1]
    assert job["ba_job_id"] == "BA-67890"
    assert job["employment_type"] == "part_time"
    assert job["location_city"] == "München"
    assert job["location_state"] == "Bayern"


def test_parse_internship_job(ba_sample_response: bytes) -> None:
    xml = ba_sample_response.decode("utf-8")
    jobs = BundesagenturClient.parse_job_response(xml)

    job = jobs[2]
    assert job["ba_job_id"] == "BA-11111"
    assert job["employment_type"] == "internship"
    assert job["company_name"] == "WebAgency KG"
    assert job["location_city"] == "Hamburg"
    assert job["location_state"] == "Hamburg"


def test_parse_empty_response() -> None:
    xml = '<?xml version="1.0" encoding="UTF-8"?><job:jobs xmlns:job="http://www.arbeitsagentur.de/jobboerse/jobsuche/v1/schema"/>'
    jobs = BundesagenturClient.parse_job_response(xml)
    assert jobs == []


@pytest.mark.asyncio
async def test_daily_limit_enforcement() -> None:
    client = BundesagenturClient(api_key="test-key", daily_limit=0)

    with pytest.raises(RuntimeError, match="Daily API limit"):
        await client.search_jobs(keywords="test")

    await client.close()
