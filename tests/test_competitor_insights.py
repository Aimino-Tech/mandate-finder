import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.company import Company
from src.models.competitor import CampaignActivity, CompanyPrivacy, CompanySignal
from src.services.competitor_insights import (
    get_alternative_companies,
    get_competitor_insight,
    get_signal_timeline,
)
from src.workers.signal_aggregator import aggregate_company_signals


async def add_activity(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_index: int,
    days_ago: int = 0,
):
    activity = CampaignActivity(
        id=uuid.uuid4(),
        company_id=company_id,
        user_id=uuid.uuid5(uuid.NAMESPACE_DNS, f"user-{user_index}"),
        activity_type="outreach",
        created_at=datetime.now(UTC) - timedelta(days=days_ago),
    )
    db.add(activity)
    await db.flush()


async def add_signal(
    db: AsyncSession,
    company_id: uuid.UUID,
    count: int,
    trend: str = "stable",
    score: float = 0.0,
):
    signal = CompanySignal(
        id=uuid.uuid4(),
        company_id=company_id,
        competitor_count=count,
        trend=trend,
        competition_score=score,
    )
    db.add(signal)
    await db.flush()


class TestCompetitorInsights:
    async def test_5_users_targeting_company_shows_5_active(
        self, db_session: AsyncSession, company_a: Company
    ):
        for i in range(5):
            await add_activity(db_session, company_a.id, user_index=i, days_ago=i)
        await add_signal(db_session, company_a.id, count=5, score=0.25)

        insight = await get_competitor_insight(str(company_a.id), db_session)

        assert insight is not None
        assert insight["company_name"] == "Siemens AG"
        assert insight["competitor_count"] == 5
        assert insight["competition_level"] == "medium"
        assert insight["anonymized"] is True

    async def test_2_users_targeting_company_shows_low_competition_k_anonymity(
        self, db_session: AsyncSession, company_b: Company
    ):
        for i in range(2):
            await add_activity(db_session, company_b.id, user_index=i)
        await add_signal(db_session, company_b.id, count=2, score=0.0)

        insight = await get_competitor_insight(str(company_b.id), db_session)

        assert insight is not None
        assert insight["competitor_count"] == 0
        assert insight["competition_level"] == "low"
        assert insight["competition_score"] == 0.0

    async def test_opted_out_company_excluded_from_aggregation(
        self, db_session: AsyncSession, company_a: Company
    ):
        for i in range(10):
            await add_activity(db_session, company_a.id, user_index=i)

        privacy = CompanyPrivacy(
            id=uuid.uuid4(),
            company_id=company_a.id,
            opted_out=True,
        )
        db_session.add(privacy)
        await add_signal(db_session, company_a.id, count=10, score=0.5)
        await db_session.flush()

        insight = await get_competitor_insight(str(company_a.id), db_session)

        assert insight is None

    async def test_unwatched_company_returns_empty_not_error(
        self, db_session: AsyncSession
    ):
        unknown_id = uuid.uuid4()
        insight = await get_competitor_insight(str(unknown_id), db_session)

        assert insight is None

    async def test_alternative_companies_with_lower_competition(
        self,
        db_session: AsyncSession,
        company_a: Company,
        company_b: Company,
        company_c: Company,
    ):
        await add_signal(db_session, company_a.id, count=15, score=0.75)
        await add_signal(db_session, company_b.id, count=5, score=0.25)
        await add_signal(db_session, company_c.id, count=8, score=0.40)

        for i in range(15):
            await add_activity(db_session, company_a.id, user_index=i)
        for i in range(5):
            await add_activity(db_session, company_b.id, user_index=i)
        for i in range(8):
            await add_activity(db_session, company_c.id, user_index=i)

        await db_session.flush()

        alternatives = await get_alternative_companies(
            str(company_a.id), db_session, limit=5
        )

        assert len(alternatives) > 0
        for alt in alternatives:
            assert alt["competitor_count"] < 15
            assert alt["anonymized"] is True

    async def test_no_signal_for_unwatched_returns_empty_alternatives(
        self, db_session: AsyncSession, company_a: Company
    ):
        unknown_id = uuid.uuid4()
        alternatives = await get_alternative_companies(
            str(unknown_id), db_session
        )

        assert alternatives == []

    async def test_signal_timeline_for_low_activity_returns_empty(
        self, db_session: AsyncSession, company_b: Company
    ):
        for i in range(2):
            await add_activity(db_session, company_b.id, user_index=i)

        timeline = await get_signal_timeline(str(company_b.id), db_session)

        assert timeline == []

    async def test_zero_competitors_returns_empty_insight(
        self, db_session: AsyncSession, company_a: Company
    ):
        await add_signal(db_session, company_a.id, count=0, score=0.0)

        insight = await get_competitor_insight(str(company_a.id), db_session)

        assert insight is not None
        assert insight["competitor_count"] == 0
        assert insight["competition_level"] == "low"


class TestSignalAggregator:
    async def test_aggregate_updates_signal_for_active_company(
        self, db_session: AsyncSession, company_a: Company
    ):
        for i in range(5):
            await add_activity(
                db_session, company_a.id, user_index=i, days_ago=i * 10
            )
        await db_session.flush()

        count = await aggregate_company_signals(db_session)

        assert count == 1

        result = await db_session.execute(
            select(CompanySignal).where(CompanySignal.company_id == company_a.id)
        )
        signal = result.scalar_one_or_none()
        assert signal is not None
        assert signal.competitor_count == 5
        assert signal.trend in ("increasing", "stable", "decreasing")
        assert signal.competition_score > 0

    async def test_aggregate_excludes_opted_out_company(
        self, db_session: AsyncSession, company_a: Company
    ):
        for i in range(10):
            await add_activity(db_session, company_a.id, user_index=i)

        privacy = CompanyPrivacy(
            id=uuid.uuid4(), company_id=company_a.id, opted_out=True
        )
        db_session.add(privacy)
        await db_session.flush()

        count = await aggregate_company_signals(db_session)

        if count > 0:
            result = await db_session.execute(
                select(CompanySignal).where(CompanySignal.company_id == company_a.id)
            )
            signal = result.scalar_one_or_none()
            assert signal is None or signal.competitor_count == 0


class TestAPIResponses:
    async def test_insight_endpoint_returns_expected_structure(
        self, db_session: AsyncSession, company_a: Company
    ):
        for i in range(5):
            await add_activity(db_session, company_a.id, user_index=i)
        await add_signal(db_session, company_a.id, count=5, score=0.25)
        await db_session.flush()

        insight = await get_competitor_insight(str(company_a.id), db_session)

        assert insight is not None
        expected_keys = {
            "company_id", "company_name", "competitor_count",
            "competition_level", "trend", "competition_score",
            "signal_timeline", "anonymized",
        }
        assert set(insight.keys()) == expected_keys
        assert insight["company_name"] == "Siemens AG"
        assert isinstance(insight["competitor_count"], int)
        assert isinstance(insight["competition_score"], float)

    async def test_timeline_endpoint_structure(
        self, db_session: AsyncSession, company_a: Company
    ):
        for i in range(5):
            await add_activity(
                db_session, company_a.id, user_index=i, days_ago=i * 7
            )
        await add_signal(db_session, company_a.id, count=5, score=0.25)
        await db_session.flush()

        timeline = await get_signal_timeline(str(company_a.id), db_session, days=90)

        assert isinstance(timeline, list)
