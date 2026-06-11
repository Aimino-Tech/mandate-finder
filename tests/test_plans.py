from src.models.billing import Feature, PlanTier
from src.services.billing.plans import (
    ALL_PLANS,
    get_features_for_tier,
    get_max_team_members,
    get_plan_config,
    requires_feature,
)


def test_all_plans_defined():
    assert PlanTier.solo in ALL_PLANS
    assert PlanTier.professional in ALL_PLANS
    assert PlanTier.agency in ALL_PLANS


def test_solo_plan():
    solo = ALL_PLANS[PlanTier.solo]
    assert solo.price_eur == 49.0
    assert solo.max_team_members == 1
    assert solo.trial_days == 14
    assert Feature.search in solo.features
    assert Feature.outreach not in solo.features


def test_professional_plan():
    pro = ALL_PLANS[PlanTier.professional]
    assert pro.price_eur == 199.0
    assert pro.max_team_members == 5
    assert Feature.search in pro.features
    assert Feature.outreach in pro.features
    assert Feature.analytics not in pro.features


def test_agency_plan():
    agency = ALL_PLANS[PlanTier.agency]
    assert agency.price_eur == 499.0
    assert agency.max_team_members == 20
    assert all(f in agency.features for f in Feature)


def test_requires_feature():
    assert requires_feature(Feature.search, PlanTier.solo)
    assert not requires_feature(Feature.outreach, PlanTier.solo)
    assert requires_feature(Feature.outreach, PlanTier.professional)
    assert requires_feature(Feature.analytics, PlanTier.agency)


def test_get_plan_config():
    config = get_plan_config("solo")
    assert config is not None
    assert config.tier == PlanTier.solo

    config = get_plan_config("invalid")
    assert config is None


def test_get_features():
    features = get_features_for_tier(PlanTier.solo)
    assert Feature.search in features
    assert len(features) == 1

    features = get_features_for_tier(PlanTier.agency)
    assert len(features) == 7


def test_get_max_team_members():
    assert get_max_team_members(PlanTier.solo) == 1
    assert get_max_team_members(PlanTier.professional) == 5
    assert get_max_team_members(PlanTier.agency) == 20
