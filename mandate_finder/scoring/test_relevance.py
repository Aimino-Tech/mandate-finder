from __future__ import annotations

from mandate_finder.scoring.models import JobPosting, SearchProfile
from mandate_finder.scoring.relevance_engine import RelevanceEngine


async def test_relevance_scoring() -> None:
    profile = SearchProfile(
        keywords="Senior React Developer",
        location="Berlin",
        industries=["Tech", "Finance"],
    )

    jobs = [
        JobPosting(
            title="Senior React Developer",
            description="Senior React Developer with TypeScript for fintech platform.",
            company="FinTech GmbH",
            location="Berlin",
            skills=["React", "TypeScript", "Redux", "Node.js"],
            seniority="senior",
        ),
        JobPosting(
            title="Junior React Developer",
            description="Looking for a Junior React Developer to maintain our website.",
            company="Agency",
            location="Berlin",
            skills=["React", "HTML", "CSS"],
            seniority="junior",
        ),
        JobPosting(
            title="Java Architect",
            description="Java Architect with Spring Boot for banking systems.",
            company="Bank",
            location="München",
            skills=["Java", "Spring", "Microservices"],
            seniority="lead",
        ),
    ]

    engine = RelevanceEngine()
    results = await engine.score_all(profile, jobs)

    assert len(results) == 3
    assert results[0].score > results[1].score, (
        f"Senior React ({results[0].score}) should beat Junior React ({results[1].score})"
    )
    assert results[0].score > results[2].score, (
        f"Senior React ({results[0].score}) should beat Java Architect ({results[2].score})"
    )
    assert "Senior" in results[0].reasoning or "Senior" in str(results[0].dimensions), (
        f"Explanation should mention Senior: {results[0].reasoning}"
    )
    assert results[0].suggested_action.value == "contact_immediately", (
        f"Best match should be contact_immediately, got {results[0].suggested_action}"
    )

    for i, r in enumerate(results):
        assert 0.0 <= r.score <= 1.0, f"Result {i} score {r.score} out of range"
        assert r.reasoning, f"Result {i} missing reasoning"
        assert r.dimensions is not None, f"Result {i} missing dimensions"
        assert r.rule_score is not None, f"Result {i} missing rule_score"
        assert r.agi_score is not None, f"Result {i} missing agi_score"


async def test_empty_profile() -> None:
    profile = SearchProfile(keywords="")
    jobs = [
        JobPosting(
            title="Anything Developer",
            description="Some generic job description.",
            company="Generic Corp",
            location="Anywhere",
        ),
    ]
    engine = RelevanceEngine()
    results = await engine.score_all(profile, jobs)
    assert len(results) == 1
    assert 0.0 <= results[0].score <= 1.0


async def test_custom_weights() -> None:
    profile = SearchProfile(keywords="Python Developer", location="Hamburg")
    job = JobPosting(
        title="Python Developer",
        description="Python backend development with Django.",
        company="TechCo",
        location="Hamburg",
        skills=["Python", "Django"],
    )
    engine = RelevanceEngine()
    default_result = await engine.score_job(profile, job)
    assert default_result.score > 0.5

    location_heavy = engine.weights.with_overrides(location_match=0.8, title_match=0.05)
    heavy_engine = RelevanceEngine(weights=location_heavy)
    heavy_result = await heavy_engine.score_job(profile, job)
    assert heavy_result.score > 0.0
