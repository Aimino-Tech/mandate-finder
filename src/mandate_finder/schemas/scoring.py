from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ScoreJobRequest(BaseModel):
    keywords: str = Field(..., description="Search keywords (e.g. 'Senior React Developer')")
    location: str = Field("", description="Target location")
    industries: List[str] = Field(default_factory=list, description="Target industries")
    skills: List[str] = Field(default_factory=list, description="Required skills")
    seniority: str = Field("", description="Seniority level")
    min_score: float = Field(0.0, ge=0.0, le=1.0)
    custom_weights: Dict[str, float] = Field(default_factory=dict)

    title: str = Field(..., description="Job title")
    description: str = Field("", description="Job description")
    company: str = Field("", description="Company name")
    location: str = Field("", description="Job location")
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
    industries: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    seniority: str = Field("")
    min_score: float = Field(0.0, ge=0.0, le=1.0)
    custom_weights: Dict[str, float] = Field(default_factory=dict)

    jobs: List[Dict[str, Any]] = Field(..., description="List of jobs to score")


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
