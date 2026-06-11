from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class SuggestedAction(str, Enum):
    CONTACT_IMMEDIATELY = "contact_immediately"
    ADD_TO_WATCHLIST = "add_to_watchlist"
    SKIP = "skip"


@dataclass
class SearchProfile:
    keywords: str
    location: Optional[str] = None
    radius_km: Optional[int] = None
    industries: List[str] = field(default_factory=list)
    min_salary: Optional[int] = None
    employment_type: Optional[str] = None
    exclusions: List[str] = field(default_factory=list)
    min_seniority: Optional[str] = None
    user_feedback_history: List[dict] = field(default_factory=list)


@dataclass
class JobPosting:
    title: str
    description: str
    company: str
    location: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    employment_type: Optional[str] = None
    posted_at: Optional[str] = None
    seniority: Optional[str] = None


@dataclass
class MatchDimensions:
    title_match: float = 0.0
    skills_match: float = 0.0
    location_match: float = 0.0
    industry_match: float = 0.0
    seniority_match: float = 0.0

    def as_dict(self) -> dict:
        return {
            "title_match": self.title_match,
            "skills_match": self.skills_match,
            "location_match": self.location_match,
            "industry_match": self.industry_match,
            "seniority_match": self.seniority_match,
        }


@dataclass
class MatchResult:
    score: float
    reasoning: str
    dimensions: MatchDimensions
    suggested_action: SuggestedAction
    urgency: Optional[str] = None
    rule_score: Optional[float] = None
    agi_score: Optional[float] = None
