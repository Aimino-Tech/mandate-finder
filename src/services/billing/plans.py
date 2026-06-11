from __future__ import annotations

from dataclasses import dataclass, field

from src.models.billing import Feature, PlanTier


@dataclass
class PlanConfig:
    tier: PlanTier
    name: str
    price_eur: float
    trial_days: int = 14
    description: str = ""
    features: set[Feature] = field(default_factory=set)
    max_team_members: int = 1
    sort_order: int = 0
    stripe_price_id_env: str = ""


SOLO = PlanConfig(
    tier=PlanTier.solo,
    name="Solo",
    price_eur=49.0,
    trial_days=14,
    description="Search only — perfect for individual recruiters",
    features={Feature.search},
    max_team_members=1,
    sort_order=0,
    stripe_price_id_env="STRIPE_SOLO_PRICE_ID",
)

PROFESSIONAL = PlanConfig(
    tier=PlanTier.professional,
    name="Professional",
    price_eur=199.0,
    trial_days=14,
    description="Search + outreach — for active sourcing",
    features={Feature.search, Feature.outreach},
    max_team_members=5,
    sort_order=1,
    stripe_price_id_env="STRIPE_PROFESSIONAL_PRICE_ID",
)

AGENCY = PlanConfig(
    tier=PlanTier.agency,
    name="Agency",
    price_eur=499.0,
    trial_days=14,
    description="Team + analytics + priority — for agencies",
    features={
        Feature.search,
        Feature.outreach,
        Feature.analytics,
        Feature.team_members,
        Feature.priority_support,
        Feature.api_access,
        Feature.custom_reports,
    },
    max_team_members=20,
    sort_order=2,
    stripe_price_id_env="STRIPE_AGENCY_PRICE_ID",
)

ALL_PLANS: dict[PlanTier, PlanConfig] = {
    PlanTier.solo: SOLO,
    PlanTier.professional: PROFESSIONAL,
    PlanTier.agency: AGENCY,
}


def get_plan_config(tier: str) -> PlanConfig | None:
    try:
        return ALL_PLANS.get(PlanTier(tier))
    except ValueError:
        return None


def get_features_for_tier(tier: PlanTier) -> set[Feature]:
    plan = ALL_PLANS.get(tier)
    return plan.features if plan else set()


def get_max_team_members(tier: PlanTier) -> int:
    plan = ALL_PLANS.get(tier)
    return plan.max_team_members if plan else 0


def requires_feature(required: Feature, tier: PlanTier) -> bool:
    return required in get_features_for_tier(tier)
