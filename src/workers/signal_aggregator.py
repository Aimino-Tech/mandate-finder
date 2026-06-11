import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.company import Company
from src.models.competitor import CampaignActivity, CompanyPrivacy, CompanySignal
from src.services.competitor_insights import K_ANONYMITY_THRESHOLD

logger = logging.getLogger(__name__)


async def aggregate_company_signals(db: AsyncSession) -> int:
    cutoff_90d = datetime.now(UTC) - timedelta(days=90)
    cutoff_30d = datetime.now(UTC) - timedelta(days=30)
    cutoff_7d = datetime.now(UTC) - timedelta(days=7)

    companies_result = await db.execute(
        select(Company.id, Company.is_private).where(Company.is_private.is_(False))
    )
    companies = companies_result.all()

    privacy_result = await db.execute(
        select(CompanyPrivacy.company_id).where(CompanyPrivacy.opted_out.is_(True))
    )
    opted_out_ids = {row.company_id for row in privacy_result.all()}

    updated_count = 0

    for company_id, _ in companies:
        if company_id in opted_out_ids:
            continue

        count_90d = await db.scalar(
            select(sa_func.count(sa_func.distinct(CampaignActivity.user_id)))
            .where(CampaignActivity.company_id == company_id)
            .where(CampaignActivity.created_at >= cutoff_90d)
        )
        count_90d = count_90d or 0

        count_30d = await db.scalar(
            select(sa_func.count(sa_func.distinct(CampaignActivity.user_id)))
            .where(CampaignActivity.company_id == company_id)
            .where(CampaignActivity.created_at >= cutoff_30d)
        )
        count_30d = count_30d or 0

        count_7d = await db.scalar(
            select(sa_func.count(sa_func.distinct(CampaignActivity.user_id)))
            .where(CampaignActivity.company_id == company_id)
            .where(CampaignActivity.created_at >= cutoff_7d)
        )
        count_7d = count_7d or 0

        trend = _compute_trend(count_7d, count_30d, count_90d)
        competition_score = _compute_score(count_90d)
        timeline_data = await _build_timeline(company_id, db, cutoff_90d)

        existing = await db.scalar(
            select(CompanySignal).where(CompanySignal.company_id == company_id)
        )

        if existing:
            existing.competitor_count = count_90d
            existing.trend = trend
            existing.competition_score = competition_score
            existing.signal_timeline_json = json.dumps(timeline_data)
            existing.updated_at = datetime.now(UTC)
        else:
            signal = CompanySignal(
                company_id=company_id,
                competitor_count=count_90d,
                trend=trend,
                competition_score=competition_score,
                signal_timeline_json=json.dumps(timeline_data),
            )
            db.add(signal)

        updated_count += 1

    await db.commit()
    logger.info("Aggregated signals for %d companies", updated_count)
    return updated_count


async def _build_timeline(
    company_id, db: AsyncSession, cutoff: datetime
) -> list[dict]:
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
            timeline.append({
                "week": week_iso,
                "active_agencies": row.count,
            })
    return timeline


def _compute_trend(count_7d: int, count_30d: int, count_90d: int) -> str:
    if count_90d == 0:
        return "stable"
    ratio_30d = count_30d / max(count_90d, 1) * 3
    ratio_7d = count_7d / max(count_90d, 1) * 12

    avg_ratio = (ratio_30d + ratio_7d) / 2
    if avg_ratio > 1.3:
        return "increasing"
    if avg_ratio < 0.7:
        return "decreasing"
    return "stable"


def _compute_score(count_90d: int) -> float:
    if count_90d < K_ANONYMITY_THRESHOLD:
        return 0.0
    raw = min(count_90d / 20.0, 1.0)
    return round(raw, 2)
