"""Tests for the multi-level dedup engine and job normalizer (AIM-1489).

These tests exercise pure logic only — they do NOT require a database.
"""

from __future__ import annotations

import pytest

from mandate_finder.scrapers.job_dedup import (
    DedupDecision,
    JobDedupEngine,
    compute_fingerprint,
)
from mandate_finder.scrapers.job_normalizer import JobNormalizer

# Make pytest-asyncio use function-scoped event loop for these tests


# These tests are pure logic — they do NOT need a database.
# Override the autouse DB fixture from conftest.py with a no-op.
@pytest.fixture(autouse=True)
def setup_db() -> None:
    """No-op: skip database setup for unit tests."""
    return None


# ======================================================================
# JobNormalizer tests
# ======================================================================


class TestJobNormalizer:
    def test_normalize_title_senior(self):
        assert JobNormalizer.normalize_title("Sr. Full Stack Eng. (m/f/x)") == "Senior Full Stack Engineer"

    def test_normalize_title_junior(self):
        assert JobNormalizer.normalize_title("Jr. React Dev.") == "Junior React Developer"

    def test_normalize_title_vp(self):
        assert JobNormalizer.normalize_title("VP of Engineering") == "Vice President of Engineering"

    def test_normalize_title_no_change(self):
        assert JobNormalizer.normalize_title("Senior React Developer") == "Senior React Developer"

    def test_normalize_title_german_removed(self):
        result = JobNormalizer.normalize_title("Software Engineer (m/w/d) in Vollzeit")
        assert "(m/w/d)" not in result
        assert "in Vollzeit" not in result
        assert "Software Engineer" in result

    def test_extract_salary_euro_range(self):
        result = JobNormalizer.extract_salary("Salary: €60.000 - €80.000 per year")
        assert result["salary_min"] == 60000
        assert result["salary_max"] == 80000
        assert result["salary_currency"] == "EUR"

    def test_extract_salary_dollar_k(self):
        result = JobNormalizer.extract_salary("Compensation: $100k-$120k")
        assert result["salary_min"] == 100000
        assert result["salary_max"] == 120000
        assert result["salary_currency"] == "USD"

    def test_extract_salary_no_match(self):
        result = JobNormalizer.extract_salary("No salary info here")
        assert result["salary_min"] is None
        assert result["salary_max"] is None

    def test_extract_skills(self):
        desc = "We need a Python developer with React experience and AWS."
        skills = JobNormalizer.extract_skills(desc)
        assert "python" in skills
        assert "react" in skills
        assert "aws" in skills

    def test_extract_skills_empty(self):
        assert JobNormalizer.extract_skills("") == []

    def test_classify_employment_type_fulltime(self):
        assert JobNormalizer.classify_employment_type("Full-time position") == "full-time"

    def test_classify_employment_type_freelance(self):
        assert JobNormalizer.classify_employment_type("Freelance position (selbstständig)") == "freelance"

    def test_classify_employment_type_internship(self):
        assert JobNormalizer.classify_employment_type("Internship (Praktikum)") == "internship"

    def test_classify_employment_type_unknown(self):
        assert JobNormalizer.classify_employment_type("") == "unknown"


# ======================================================================
# Fingerprint computation
# ======================================================================


class TestFingerprint:
    def test_compute_fingerprint_consistent(self):
        a = {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"}
        b = {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"}
        assert compute_fingerprint(a) == compute_fingerprint(b)

    def test_compute_fingerprint_different(self):
        a = {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"}
        b = {"title": "Java Backend Developer", "company_name": "Company B", "location": "München"}
        assert compute_fingerprint(a) != compute_fingerprint(b)

    def test_compute_fingerprint_case_insensitive(self):
        a = {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"}
        b = {"title": "senior react developer", "company_name": "company a", "location": "berlin"}
        assert compute_fingerprint(a) == compute_fingerprint(b)


# ======================================================================
# Dedup engine levels
# ======================================================================


@pytest.mark.parametrize(
    "a,b,expected_level",
    [
        pytest.param(
            {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin",
             "source": "linkedin", "source_job_id": "123"},
            {"title": "Sr. React Dev", "company_name": "Company A", "location": "Berlin",
             "source": "linkedin", "source_job_id": "123"},
            "EXISTING",
            id="source_id",
        ),
        pytest.param(
            {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"},
            {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"},
            "FINGERPRINT",
            id="fingerprint",
        ),
        pytest.param(
            {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"},
            {"title": "Senior Frontend Engineer", "company_name": "Company A", "location": "Berlin"},
            "MERGED",
            id="semantic",
        ),
        pytest.param(
            {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"},
            {"title": "Java Backend Developer", "company_name": "Company B", "location": "München"},
            "NEW",
            id="new",
        ),
    ],
)
@pytest.mark.asyncio
async def test_dedup_levels(a, b, expected_level):
    """Verify the four dedup levels return correct decisions
    (matching the spec's parametric test)."""
    engine = JobDedupEngine()

    # For fingerprint dedup, pre-compute the matching fingerprint on the existing record
    if expected_level == "FINGERPRINT":
        b["fingerprint_md5"] = compute_fingerprint(a)

    # For source ID dedup, give the existing record a valid UUID
    if expected_level == "EXISTING":
        b["id"] = "550e8400-e29b-41d4-a716-446655440001"

    result = await engine.check_new(a, existing=[b])
    assert result.decision.value == expected_level, f"Expected {expected_level}, got {result.decision}"
    if expected_level == "FINGERPRINT":
        assert result.confidence > 0.95
    if expected_level == "EXISTING":
        assert result.existing_id is not None


# ======================================================================
# Source ID dedup
# ======================================================================


@pytest.mark.asyncio
async def test_source_id_match():
    engine = JobDedupEngine()
    posting = {"source": "linkedin", "source_job_id": "abc-123", "title": "Engineer"}
    existing = [
        {"id": "550e8400-e29b-41d4-a716-446655440001", "source": "linkedin", "source_job_id": "abc-123", "title": "Engineer"},
    ]
    result = await engine.check_new(posting, existing=existing)
    assert result.decision == DedupDecision.EXISTING
    assert result.existing_id is not None


@pytest.mark.asyncio
async def test_source_id_no_match():
    engine = JobDedupEngine()
    posting = {"source": "linkedin", "source_job_id": "abc-123", "title": "Engineer"}
    existing = [
        {"source": "linkedin", "source_job_id": "xyz-999", "title": "Engineer"},
    ]
    result = await engine.check_new(posting, existing=existing)
    assert result.decision != DedupDecision.EXISTING


# ======================================================================
# Fingerprint dedup
# ======================================================================


@pytest.mark.asyncio
async def test_fingerprint_match():
    engine = JobDedupEngine()
    posting = {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"}
    fp = compute_fingerprint(posting)
    existing = [
        {"fingerprint_md5": fp, "title": "Senior React Developer", "company_name": "Company A",
         "location": "Berlin"},
    ]
    result = await engine.check_new(posting, existing=existing)
    assert result.decision == DedupDecision.FINGERPRINT
    assert result.confidence > 0.95


# ======================================================================
# Semantic merge dedup
# ======================================================================


@pytest.mark.asyncio
async def test_semantic_match():
    engine = JobDedupEngine()
    posting = {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"}
    existing = [
        {"title": "Senior Frontend Engineer", "company_name": "Company A", "location": "Berlin"},
    ]
    result = await engine.check_new(posting, existing=existing)
    assert result.decision == DedupDecision.MERGED
    assert result.confidence >= 0.75


@pytest.mark.asyncio
async def test_semantic_no_match():
    engine = JobDedupEngine()
    posting = {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"}
    existing = [
        {"title": "Java Backend Developer", "company_name": "Company B", "location": "München"},
    ]
    result = await engine.check_new(posting, existing=existing)
    assert result.decision == DedupDecision.NEW


# ======================================================================
# Cache dedup
# ======================================================================


@pytest.mark.asyncio
async def test_cache_match():
    engine = JobDedupEngine()
    posting = {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"}
    fp = compute_fingerprint(posting)
    cache_entries = [
        {"fingerprint_md5": fp, "merged_job_posting_id": "550e8400-e29b-41d4-a716-446655440002", "confidence": 0.95},
    ]
    result = await engine.check_new(posting, cache_entries=cache_entries)
    assert result.decision == DedupDecision.CACHE
    assert str(result.existing_id) == "550e8400-e29b-41d4-a716-446655440002"


@pytest.mark.asyncio
async def test_cache_low_confidence():
    engine = JobDedupEngine()
    posting = {"title": "Senior React Developer", "company_name": "Company A", "location": "Berlin"}
    fp = compute_fingerprint(posting)
    cache_entries = [
        {"fingerprint_md5": fp, "merged_job_posting_id": "550e8400-e29b-41d4-a716-446655440002", "confidence": 0.5},
    ]
    result = await engine.check_new(posting, cache_entries=cache_entries)
    assert result.decision != DedupDecision.CACHE


# ======================================================================
# Merge job postings
# ======================================================================


@pytest.mark.asyncio
async def test_merge_job_postings():
    primary = {
        "id": "primary-id",
        "title": "Senior Engineer",
        "company_name": "Acme",
        "skills": ["python"],
        "source_job_id": "src-001",
    }
    duplicate = {
        "id": "dup-id",
        "title": None,
        "company_name": None,
        "skills": ["python", "aws"],
        "source_job_id": "src-002",
    }
    merged = await JobDedupEngine.merge_job_postings(primary, duplicate)
    assert merged["title"] == "Senior Engineer"
    assert merged["company_name"] == "Acme"
    assert "python" in merged["skills"]
    assert "aws" in merged["skills"]
    assert "src-002" in merged["source_job_ids"]


# ======================================================================
# Edge cases
# ======================================================================


@pytest.mark.asyncio
async def test_check_new_empty_existing():
    engine = JobDedupEngine()
    posting = {"title": "Engineer", "source": "linkedin", "source_job_id": "1"}
    result = await engine.check_new(posting, existing=[])
    assert result.decision == DedupDecision.NEW


@pytest.mark.asyncio
async def test_check_new_no_fields():
    engine = JobDedupEngine()
    result = await engine.check_new({}, existing=[])
    assert result.decision == DedupDecision.NEW
