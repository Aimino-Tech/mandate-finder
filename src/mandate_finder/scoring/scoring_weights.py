from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=False)
class ScoringWeights:
    """Tunable weight configuration per scoring dimension.

    Each weight is a float between 0.0 and 1.0 representing the importance
    of that dimension in the overall relevance score. Dimensions can be
    personalised per user by creating a custom instance.
    """

    title: float = 0.25
    skills: float = 0.25
    location: float = 0.20
    industry: float = 0.15
    seniority: float = 0.15

    def __post_init__(self) -> None:
        for name, value in self.as_dict().items():
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"Weight '{name}' must be between 0.0 and 1.0, got {value}"
                )

    def as_dict(self) -> Dict[str, float]:
        return {
            "title": self.title,
            "skills": self.skills,
            "location": self.location,
            "industry": self.industry,
            "seniority": self.seniority,
        }

    @classmethod
    def from_dict(cls, weights: Dict[str, float]) -> "ScoringWeights":
        return cls(
            title=weights.get("title", 0.25),
            skills=weights.get("skills", 0.25),
            location=weights.get("location", 0.20),
            industry=weights.get("industry", 0.15),
            seniority=weights.get("seniority", 0.15),
        )

    def to_dict(self) -> Dict[str, float]:
        return self.as_dict()


DEFAULT_WEIGHTS = ScoringWeights()
