from __future__ import annotations

from typing import Any, Dict, List

import pytest

from mandate_finder.scoring.explainer import generate_explanation
from mandate_finder.scoring.relevance_engine import MatchResult, RelevanceEngine, SearchProfile, SuggestedAction
from mandate_finder.scoring.scoring_weights import DEFAULT_WEIGHTS, ScoringWeights


class TestScoringWeights:
    def test_default_weights_sum_to_one(self) -> None:
        w = DEFAULT_WEIGHTS
        total = w.title + w.skills + w.location + w.industry + w.seniority
        assert abs(total - 1.0) < 0.001

    def test_custom_weights(self) -> None:
        w = ScoringWeights(title=0.5, skills=0.3, location=0.1, industry=0.05, seniority=0.05)
        assert w.title == 0.5
        assert w.skills == 0.3

    def test_invalid_weights_raise(self) -> None:
        with pytest.raises(ValueError):
            ScoringWeights(title=1.5, skills=0.0, location=0.0, industry=0.0, seniority=0.0)

    def test_from_dict(self) -> None:
        w = ScoringWeights.from_dict({"title": 0.4, "skills": 0.3, "location": 0.2, "industry": 0.05, "seniority": 0.05})
        assert w.title == 0.4

    def test_to_dict(self) -> None:
        w = DEFAULT_WEIGHTS
        d = w.to_dict()
        assert isinstance(d, dict)
        assert "title" in d


class TestSearchProfile:
    def test_default_weights(self) -> None:
        p = SearchProfile(keywords="React Developer")
        assert p.get_weights() == DEFAULT_WEIGHTS

    def test_custom_weights(self) -> None:
        cw = ScoringWeights(title=0.5, skills=0.5, location=0.0, industry=0.0, seniority=0.0)
        p = SearchProfile(keywords="React", custom_weights=cw)
        assert p.get_weights() == cw


class TestRelevanceEngine:
    """Integration tests matching the spec."""

    @pytest.mark.asyncio
    async def test_relevance_scoring(self) -> None:
        """Test from the spec document."""
        profile = SearchProfile(
            keywords="Senior React Developer",
            location="Berlin",
            industries=["Tech", "Finance"],
        )
        jobs: List[Dict[str, Any]] = [
            {
                "title": "Senior React Developer",
                "description": "React, TypeScript, and frontend development in Berlin",
                "company": "FinTech GmbH",
                "location": "Berlin",
                "industry": "Tech",
            },
            {
                "title": "Junior React Developer",
                "description": "React, HTML, and CSS in Berlin",
                "company": "Agency",
                "location": "Berlin",
                "industry": "Tech",
            },
            {
                "title": "Java Architect",
                "description": "Spring, Java, and backend architecture in München",
                "company": "Bank",
                "location": "München",
                "industry": "Finance",
            },
        ]
        engine = RelevanceEngine()
        results = await engine.score_all(profile, jobs)
        assert len(results) == 3
        assert results[0].score > results[1].score
        assert results[0].score > results[2].score
        assert "Senior React" in results[0].reasoning or "Strong" in results[0].reasoning
        assert results[0].suggested_action == SuggestedAction.CONTACT_IMMEDIATELY

    @pytest.mark.asyncio
    async def test_score_single_job(self) -> None:
        profile = SearchProfile(keywords="Python Developer", location="Berlin")
        job = {
            "title": "Python Backend Developer",
            "description": "Python, FastAPI, PostgreSQL experience required",
            "company": "TechCo",
            "location": "Berlin",
            "industry": "Tech",
        }
        engine = RelevanceEngine()
        result = await engine.score_job(profile, job)
        assert isinstance(result, MatchResult)
        assert 0.0 <= result.score <= 1.0
        assert isinstance(result.dimensions_breakdown, dict)
        assert isinstance(result.suggested_action, SuggestedAction)

    @pytest.mark.asyncio
    async def test_score_all_returns_sorted(self) -> None:
        profile = SearchProfile(keywords="Data Scientist")
        jobs = [
            {"title": "Data Scientist", "description": "ML, Python, statistics", "company": "A", "location": "", "industry": ""},
            {"title": "Data Engineer", "description": "Python, SQL, pipelines", "company": "B", "location": "", "industry": ""},
            {"title": "Frontend Dev", "description": "React, CSS, HTML", "company": "C", "location": "", "industry": ""},
        ]
        engine = RelevanceEngine()
        results = await engine.score_all(profile, jobs)
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    @pytest.mark.asyncio
    async def test_empty_description_fallback(self) -> None:
        profile = SearchProfile(keywords="React Developer")
        job = {
            "title": "React Developer",
            "description": "",
            "company": "Test",
            "location": "",
            "industry": "",
        }
        engine = RelevanceEngine()
        result = await engine.score_job(profile, job)
        assert result.score > 0  # Should still get a score from title matching

    @pytest.mark.asyncio
    async def test_no_match(self) -> None:
        profile = SearchProfile(keywords="Rust Systems Engineer", location="Tokyo")
        job = {
            "title": "Junior QA Tester",
            "description": "Manual testing, Selenium basics",
            "company": "TestCo",
            "location": "Berlin",
            "industry": "Gaming",
        }
        engine = RelevanceEngine()
        result = await engine.score_job(profile, job)
        assert result.suggested_action == SuggestedAction.SKIP
        assert result.score < 0.4


class TestMatchResult:
    def test_match_result_fields(self) -> None:
        result = MatchResult(
            score=0.85,
            reasoning="Strong match",
            dimensions_breakdown={"title": 0.9, "skills": 0.8},
            suggested_action=SuggestedAction.CONTACT_IMMEDIATELY,
            urgency="high",
        )
        assert result.score == 0.85
        assert result.suggested_action == SuggestedAction.CONTACT_IMMEDIATELY
        assert result.urgency == "high"

    def test_suggested_action_values(self) -> None:
        assert SuggestedAction.CONTACT_IMMEDIATELY.value == "contact_immediately"
        assert SuggestedAction.ADD_TO_WATCHLIST.value == "add_to_watchlist"
        assert SuggestedAction.SKIP.value == "skip"


class TestExplainer:
    def test_generate_explanation(self) -> None:
        profile = SearchProfile(keywords="Senior React Developer", location="Berlin")
        job = {"title": "Senior React Developer", "company": "FinTech GmbH", "location": "Berlin"}
        result = MatchResult(
            score=0.92,
            reasoning="Strong match (score: 0.92)",
            dimensions_breakdown={"title": 1.0, "skills": 0.85, "location": 1.0},
            suggested_action=SuggestedAction.CONTACT_IMMEDIATELY,
            urgency="high",
        )
        explanation = generate_explanation(profile, job, [result])
        assert "Senior React Developer" in explanation
        assert "FinTech GmbH" in explanation
        assert "contact_immediately" in explanation

    def test_generate_explanation_empty_results(self) -> None:
        profile = SearchProfile(keywords="Rust Developer")
        job = {"title": "COBOL Programmer", "company": "LegacyCorp"}
        explanation = generate_explanation(profile, job, [])
        assert "Rust Developer" in explanation or "no scoring" in explanation.lower()


class TestSuggestedAction:
    def test_contact_immediately_threshold(self) -> None:
        assert RelevanceEngine._derive_action(0.7) == SuggestedAction.CONTACT_IMMEDIATELY
        assert RelevanceEngine._derive_action(0.85) == SuggestedAction.CONTACT_IMMEDIATELY

    def test_add_to_watchlist_threshold(self) -> None:
        assert RelevanceEngine._derive_action(0.4) == SuggestedAction.ADD_TO_WATCHLIST
        assert RelevanceEngine._derive_action(0.6) == SuggestedAction.ADD_TO_WATCHLIST

    def test_skip_threshold(self) -> None:
        assert RelevanceEngine._derive_action(0.0) == SuggestedAction.SKIP
        assert RelevanceEngine._derive_action(0.39) == SuggestedAction.SKIP
