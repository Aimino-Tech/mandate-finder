import math
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.ab_test import ABTest, ABTestVariant, Campaign, MessageEvent, MessageVariant
from src.services.ab_test_service import ABTestService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def campaign(db_session):
    c = Campaign(name="test-campaign", industry="tech", role_seniority="senior", company_size="enterprise")
    db_session.add(c)
    db_session.commit()
    return c


@pytest.fixture
def control_variant(db_session, campaign):
    v = MessageVariant(
        campaign_id=campaign.id, name="control", subject="Standard outreach",
        body="Hello, I wanted to reach out...", call_to_action="Schedule a call",
        personalization_level="low", channel="email", is_control=True,
    )
    db_session.add(v)
    db_session.commit()
    return v


@pytest.fixture
def test_variants(db_session, campaign):
    variants = []
    configs = [
        ("personalized_high", "High personalization", "Hello {{name}}, I noticed your work at {{company}}...", "high"),
        ("personalized_medium", "Medium personalization", "Hi {{name}}, wanted to connect...", "medium"),
        ("direct_cta", "Direct call-to-action", "Book a demo today!", "low"),
    ]
    for name, subject, body, pl in configs:
        v = MessageVariant(
            campaign_id=campaign.id, name=name, subject=subject, body=body,
            call_to_action="Reply for details", personalization_level=pl, channel="email",
        )
        db_session.add(v)
        variants.append(v)
    db_session.commit()
    return variants


@pytest.fixture
def ab_test(db_session, campaign, control_variant, test_variants):
    t = ABTest(campaign_id=campaign.id, name="email-outreach-test", metric="reply_rate",
               significance_threshold=0.05, min_sample_size=30)
    db_session.add(t)
    db_session.flush()
    for v in [control_variant] + test_variants:
        db_session.add(ABTestVariant(ab_test_id=t.id, variant_id=v.id))
    db_session.commit()
    return t


def _send_messages(db, variant, count, reply_rate=0.0, open_rate=0.0):
    for i in range(count):
        replied_at = datetime.utcnow() if (i / count) < reply_rate else None
        opened_at = datetime.utcnow() if (i / count) < open_rate else None
        event = MessageEvent(
            variant_id=variant.id, recipient=f"user{i}@test.com",
            sent_at=datetime.utcnow(), opened_at=opened_at, replied_at=replied_at,
        )
        db.add(event)
    db.commit()


class TestChiSquared:
    def test_all_variants_similar(self, db_session, ab_test, control_variant, test_variants):
        for v in [control_variant] + test_variants:
            _send_messages(db_session, v, 25, reply_rate=0.1, open_rate=0.3)
        service = ABTestService(db_session)
        result = service.run_chi_squared_opens(ab_test)
        assert "p_value" in result
        assert "significant" in result

    def test_one_variant_outperforms(self, db_session, ab_test, control_variant, test_variants):
        _send_messages(db_session, control_variant, 25, open_rate=0.2)
        for v in test_variants:
            rate = 0.8 if v.name == "personalized_high" else 0.25
            _send_messages(db_session, v, 25, open_rate=rate)
        service = ABTestService(db_session)
        result = service.run_chi_squared_opens(ab_test)
        high_variant = next(c for c in result["comparisons"] if c["variant_name"] == "personalized_high")
        assert high_variant["p_value"] < 0.05

    def test_insufficient_data_returns_no_error(self, db_session, ab_test, control_variant, test_variants):
        for v in [control_variant] + test_variants:
            _send_messages(db_session, v, 1)
        service = ABTestService(db_session)
        result = service.run_chi_squared_opens(ab_test)
        assert not result["significant"]


class TestMannWhitney:
    def test_reply_rate_detection(self, db_session, ab_test, control_variant, test_variants):
        _send_messages(db_session, control_variant, 40, reply_rate=0.1)
        for v in test_variants:
            rate = 0.6 if v.name == "personalized_medium" else 0.15
            _send_messages(db_session, v, 40, reply_rate=rate)
        service = ABTestService(db_session)
        result = service.run_mann_whitney_reply(ab_test)
        assert result["significant"] or result["p_value"] < 0.1


class TestAutoPromote:
    def test_promote_winner_at_significance(self, db_session, ab_test, control_variant, test_variants):
        _send_messages(db_session, control_variant, 30, reply_rate=0.05)
        for v in test_variants:
            rate = 0.45 if v.name == "direct_cta" else 0.08
            _send_messages(db_session, v, 30, reply_rate=rate)
        service = ABTestService(db_session)
        result = service.auto_promote(ab_test)
        assert result is not None
        assert result.winning_variant_id is not None
        assert result.status == "completed"

    def test_no_promote_below_min_sample(self, db_session, ab_test, control_variant, test_variants):
        _send_messages(db_session, control_variant, 5, reply_rate=0.05)
        for v in test_variants:
            _send_messages(db_session, v, 5, reply_rate=0.5)
        service = ABTestService(db_session)
        result = service.auto_promote(ab_test)
        assert result is None

    def test_no_promote_if_not_significant(self, db_session, ab_test, control_variant, test_variants):
        _send_messages(db_session, control_variant, 30, reply_rate=0.1)
        for v in test_variants:
            _send_messages(db_session, v, 30, reply_rate=0.1)
        service = ABTestService(db_session)
        result = service.auto_promote(ab_test)
        assert result is None


class TestStatisticsConvergence:
    def test_convergence_with_large_sample(self, db_session, ab_test, control_variant, test_variants):
        for v in [control_variant] + test_variants:
            _send_messages(db_session, v, 25, reply_rate=0.10)
        service = ABTestService(db_session)
        chi_result = service.run_chi_squared_opens(ab_test)
        mw_result = service.run_mann_whitney_reply(ab_test)
        assert not chi_result["significant"]
        assert not mw_result["significant"]


class TestThompsonSampling:
    def test_selects_best_variant(self, db_session, ab_test, control_variant, test_variants):
        _send_messages(db_session, control_variant, 50, reply_rate=0.05)
        _send_messages(db_session, test_variants[0], 50, reply_rate=0.55)
        _send_messages(db_session, test_variants[1], 50, reply_rate=0.25)
        _send_messages(db_session, test_variants[2], 50, reply_rate=0.15)
        service = ABTestService(db_session)
        selections = {"personalized_high": 0, "personalized_medium": 0, "direct_cta": 0, "control": 0}
        for _ in range(100):
            chosen = service.thompson_sampling_select(ab_test)
            selections[chosen.name] += 1
        assert selections["personalized_high"] > selections["direct_cta"]


class TestAdaptivePool:
    def test_deprecates_low_performers(self, db_session, ab_test, control_variant, test_variants):
        _send_messages(db_session, control_variant, 30, reply_rate=0.40)
        _send_messages(db_session, test_variants[0], 30, reply_rate=0.45)
        _send_messages(db_session, test_variants[1], 30, reply_rate=0.10)
        _send_messages(db_session, test_variants[2], 30, reply_rate=0.08)
        service = ABTestService(db_session)
        suggestions = service.adapt_variant_pool(ab_test)
        deprecated = [s for s in suggestions if s["action"] == "deprecate"]
        assert len(deprecated) > 0


class TestVariantPerformance:
    def test_export_includes_metrics(self, db_session, ab_test, control_variant, test_variants):
        _send_messages(db_session, control_variant, 20, reply_rate=0.1, open_rate=0.3)
        _send_messages(db_session, test_variants[0], 20, reply_rate=0.2, open_rate=0.4)
        service = ABTestService(db_session)
        report = [service.get_variant_performance(av.variant) for av in ab_test.variants]
        for entry in report:
            assert "variant_id" in entry
            assert "variant_name" in entry
            assert "sent" in entry
            assert "open_rate" in entry
            assert "reply_rate" in entry
            assert "meeting_rate" in entry
