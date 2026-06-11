from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from mandate_finder.scoring.explainer import generate_explanation
from mandate_finder.scoring.relevance_engine import (
    MatchResult,
    RelevanceEngine,
    SearchProfile,
    SuggestedAction,
)
from mandate_finder.scoring.scoring_weights import DEFAULT_WEIGHTS, ScoringWeights

router = APIRouter(prefix="/scoring", tags=["scoring"])


# ── Request / Response Models ─────────────────────────────────────────


class ScoreJobRequest(BaseModel):
    keywords: str = Field(..., description="Search keywords (e.g. 'Senior React Developer')")
    location: str = Field("", description="Target location")
    industries: List[str] = Field(default_factory=list, description="Target industries")
    skills: List[str] = Field(default_factory=list, description="Required skills")
    seniority: str = Field("", description="Seniority level (junior/mid/senior)")
    min_score: float = Field(0.0, ge=0.0, le=1.0, description="Minimum score threshold")
    custom_weights: Dict[str, float] = Field(default_factory=dict, description="Custom weights per dimension")

    title: str = Field(..., description="Job title")
    description: str = Field("", description="Job description")
    company: str = Field("", description="Company name")
    job_location: str = Field("", alias="location", description="Job location")
    industry: str = Field("", description="Job industry")
    job_skills: List[str] = Field(default_factory=list, alias="skills", description="Job skills")


class ScoreJobResponse(BaseModel):
    score: float
    reasoning: str
    dimensions_breakdown: Dict[str, float]
    suggested_action: str
    urgency: str
    explanation: str


class ScoreBatchRequest(BaseModel):
    keywords: str = Field(..., description="Search keywords")
    location: str = Field("", description="Target location")
    industries: List[str] = Field(default_factory=list, description="Target industries")
    skills: List[str] = Field(default_factory=list, description="Required skills")
    seniority: str = Field("", description="Seniority level")
    min_score: float = Field(0.0, ge=0.0, le=1.0)
    custom_weights: Dict[str, float] = Field(default_factory=dict)

    jobs: List[Dict[str, Any]] = Field(..., description="List of job dicts to score")


class ScoreBatchResponse(BaseModel):
    results: List[ScoreJobResponse]
    total: int
    above_threshold: int


class DimensionInfo(BaseModel):
    name: str
    description: str
    default_weight: float
    range: str = "0.0 - 1.0"


class DimensionsResponse(BaseModel):
    dimensions: List[DimensionInfo]


# ── Routes ────────────────────────────────────────────────────────────


@router.post("/score", response_model=ScoreJobResponse)
async def score_single_job(request: ScoreJobRequest) -> ScoreJobResponse:
    """Score a single job against a search profile."""
    weights = _build_weights(request.custom_weights)

    profile = SearchProfile(
        keywords=request.keywords,
        location=request.location,
        industries=request.industries,
        skills=request.skills,
        seniority=request.seniority,
        min_score=request.min_score,
        custom_weights=weights,
    )

    job: Dict[str, Any] = {
        "title": request.title,
        "description": request.description,
        "company": request.company,
        "location": request.job_location,
        "industry": request.industry,
        "skills": request.job_skills,
    }

    engine = RelevanceEngine()
    result: MatchResult = await engine.score_job(profile, job)

    explanation = generate_explanation(profile, job, [result])

    return ScoreJobResponse(
        score=result.score,
        reasoning=result.reasoning,
        dimensions_breakdown=result.dimensions_breakdown,
        suggested_action=result.suggested_action.value,
        urgency=result.urgency,
        explanation=explanation,
    )


@router.post("/score-batch", response_model=ScoreBatchResponse)
async def score_batch_jobs(request: ScoreBatchRequest) -> ScoreBatchResponse:
    """Score multiple jobs against a search profile."""
    weights = _build_weights(request.custom_weights)

    profile = SearchProfile(
        keywords=request.keywords,
        location=request.location,
        industries=request.industries,
        skills=request.skills,
        seniority=request.seniority,
        min_score=request.min_score,
        custom_weights=weights,
    )

    engine = RelevanceEngine()
    results = await engine.score_all(profile, request.jobs)

    response_results: List[ScoreJobResponse] = []
    for i, result in enumerate(results):
        job = request.jobs[i] if i < len(request.jobs) else {}
        explanation = generate_explanation(profile, job, [result])
        response_results.append(
            ScoreJobResponse(
                score=result.score,
                reasoning=result.reasoning,
                dimensions_breakdown=result.dimensions_breakdown,
                suggested_action=result.suggested_action.value,
                urgency=result.urgency,
                explanation=explanation,
            )
        )

    above = sum(1 for r in results if r.score >= profile.min_score)

    return ScoreBatchResponse(
        results=response_results,
        total=len(results),
        above_threshold=above,
    )


@router.get("/dimensions", response_model=DimensionsResponse)
async def list_dimensions() -> DimensionsResponse:
    """List available scoring dimensions with their descriptions and default weights."""
    dimensions = [
        DimensionInfo(
            name="title",
            description="Job title relevance to search keywords",
            default_weight=DEFAULT_WEIGHTS.title,
        ),
        DimensionInfo(
            name="skills",
            description="Skill overlap between profile and job",
            default_weight=DEFAULT_WEIGHTS.skills,
        ),
        DimensionInfo(
            name="location",
            description="Geographic location match",
            default_weight=DEFAULT_WEIGHTS.location,
        ),
        DimensionInfo(
            name="industry",
            description="Industry sector alignment",
            default_weight=DEFAULT_WEIGHTS.industry,
        ),
        DimensionInfo(
            name="seniority",
            description="Experience/seniority level alignment",
            default_weight=DEFAULT_WEIGHTS.seniority,
        ),
    ]
    return DimensionsResponse(dimensions=dimensions)


# ── Helpers ───────────────────────────────────────────────────────────


def _build_weights(custom: Dict[str, float]) -> ScoringWeights | None:
    """Build custom ScoringWeights from a dict, or None if empty."""
    if not custom:
        return None
    # Validate weights
    for name in custom:
        if name not in ("title", "skills", "location", "industry", "seniority"):
            raise HTTPException(
                status_code=422,
                detail=f"Unknown dimension '{name}'. Valid dimensions: title, skills, location, industry, seniority",
            )
    try:
        return ScoringWeights.from_dict(custom)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
