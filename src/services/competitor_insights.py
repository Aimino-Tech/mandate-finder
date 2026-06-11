import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.company import Company
from src.models.competitor import CampaignActivity, CompanyPrivacy, CompanySignal

K_ANONYMITY_THRESHOLD = 3


async def get_competitor_insight(
    company_id: str, db: AsyncSession
) -> dict | None:
    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        return None

    privacy = await db.execute(
        select(CompanyPrivacy).where(CompanyPrivacy.company_id == company_id)
    )
    privacy_entry = privacy.scalar_one_or_none()
    if privacy_entry and privacy_entry.opted_out:
        return None

    signal = await db.execute(
        select(CompanySignal).where(CompanySignal.company_id == company_id)
    )
    signal_entry = signal.scalar_one_or_none()

    if not signal_entry or signal_entry.competitor_count < K_ANONYMITY_THRESHOLD:
        return {
            "company_id": str(company_id),
            "company_name": company.name,
            "competitor_count": 0,
            "competition_level": "low",
            "trend": "stable",
            "competition_score": 0.0,
            "signal_timeline": [],
            "anonymized": True,
        }

    timeline = []
    if signal_entry.signal_timeline_json:
        timeline = json.loads(signal_entry.signal_timeline_json)

    competition_level = _compute_competition_level(signal_entry.competitor_count)

    return {
        "company_id": str(company_id),
        "company_name": company.name,
        "competitor_count": signal_entry.competitor_count,
        "competition_level": competition_level,
        "trend": signal_entry.trend,
        "competition_score": signal_entry.competition_score,
        "signal_timeline": timeline,
        "anonymized": True,
    }


async def get_signal_timeline(
    company_id: str, db: AsyncSession, days: int = 90
) -> list[dict]:
    cutoff = datetime.now(UTC) - timedelta(days=days)

    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        return []

    count_result = await db.execute(
        select(sa_func.count(sa_func.distinct(CampaignActivity.user_id)))
        .where(CampaignActivity.company_id == company_id)
        .where(CampaignActivity.created_at >= cutoff)
    )
    total_active = count_result.scalar()

    if total_active is None or total_active < K_ANONYMITY_THRESHOLD:
        return []

    rows_result = await db.execute(
        select(
            sa_func.date_trunc("week", CampaignActivity.created_at).label("week"),
            sa_func.count(sa_func.distinct(CampaignActivity.user_id)).label("count"),
        )
        .where(CampaignActivity.company_id == company_id)
        .where(CampaignActivity.created_at >= cutoff)
        .group_by(sa_func.date_trunc("week", CampaignActivity.created_at))
        .order_by(sa_func.date_trunc("week", CampaignActivity.created_at))
    )
    rows = rows_result.all()

    timeline = []
    for row in rows:
        week_start = row.week
        if isinstance(week_start, datetime):
            week_iso = week_start.strftime("%Y-%m-%d")
            weekly_count = row.count
            timeline.append({
                "week": week_iso,
                "active_agencies": weekly_count,
                "anonymized": True,
            })

    return timeline


async def get_alternative_companies(
    company_id: str, db: AsyncSession, limit: int = 5
) -> list[dict]:
    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        return []

    source_signal = await db.execute(
        select(CompanySignal).where(CompanySignal.company_id == company_id)
    )
    source_signal_entry = source_signal.scalar_one_or_none()
    source_count = (
        source_signal_entry.competitor_count if source_signal_entry else 0
    )

    alternatives_query = (
        select(
            Company.id,
            Company.name,
            Company.industry,
            CompanySignal.competitor_count,
            CompanySignal.competition_score,
        )
        .join(CompanySignal, Company.id == CompanySignal.company_id)
        .where(Company.id != company_id)
        .where(Company.is_private.is_(False))
        .where(CompanySignal.competitor_count < source_count)
        .where(CompanySignal.competitor_count >= K_ANONYMITY_THRESHOLD)
        .order_by(CompanySignal.competition_score.asc())
        .limit(limit)
    )

    if company.industry:
        alternatives_query = alternatives_query.where(
            Company.industry == company.industry
        )

    alt_result = await db.execute(alternatives_query)
    alternatives = alt_result.all()

    return [
        {
            "company_id": str(row.id),
            "company_name": row.name,
            "industry": row.industry,
            "competitor_count": row.competitor_count,
            "competition_score": row.competition_score,
            "anonymized": True,
        }
        for row in alternatives
    ]


def _compute_competition_level(count: int) -> str:
    if count < K_ANONYMITY_THRESHOLD:
        return "low"
    if count < 7:
        return "medium"
    if count < 15:
        return "high"
    return "very_high"
