from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

DEFAULT_WEIGHTS: Dict[str, float] = {
    "title_match": 0.30,
    "skills_match": 0.25,
    "location_match": 0.20,
    "industry_match": 0.15,
    "seniority_match": 0.10,
}

DEFAULT_PRIORITIES: Dict[str, int] = {
    "title_match": 1,
    "skills_match": 2,
    "location_match": 3,
    "industry_match": 4,
    "seniority_match": 5,
}

DEFAULT_RULE_WEIGHT: float = 0.3
DEFAULT_AGI_WEIGHT: float = 0.7


@dataclass
class ScoringWeights:
    dimension_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    dimension_priorities: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_PRIORITIES))
    rule_weight: float = DEFAULT_RULE_WEIGHT
    agi_weight: float = DEFAULT_AGI_WEIGHT

    def __post_init__(self) -> None:
        total = sum(self.dimension_weights.values())
        if abs(total - 1.0) > 0.01:
            self.dimension_weights = {
                k: v / total for k, v in self.dimension_weights.items()
            }

    def get_weight(self, dimension: str) -> float:
        return self.dimension_weights.get(dimension, 0.0)

    def get_priority(self, dimension: str) -> int:
        return self.dimension_priorities.get(dimension, 99)

    def with_overrides(self, **overrides: float) -> ScoringWeights:
        new_weights = dict(self.dimension_weights)
        new_weights.update(
            {k: v for k, v in overrides.items() if k in new_weights}
        )
        rule_w = overrides.get("rule_weight", self.rule_weight)
        agi_w = overrides.get("agi_weight", self.agi_weight)
        return ScoringWeights(
            dimension_weights=new_weights,
            dimension_priorities=dict(self.dimension_priorities),
            rule_weight=rule_w,
            agi_weight=agi_w,
        )
