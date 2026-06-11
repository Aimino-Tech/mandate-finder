"""Competitor insights service with k-anonymity guarantees.

All competitor counts below 3 (k-anonymity threshold) are hidden to protect
the identity of individual agencies targeting a company.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.activity_event import ActivityEvent
from mandate_finder.models.company_signal import CompanySignal
from mandate_finder.models.company_watchlist import CompanyWatchlist

logger = logging.getLogger(__name__)

K_ANONYMITY_THRESHOLD = 3


def _apply_k_anonymity(count: int) -> int:
    """Hide counts below the k-anonymity threshold."""
    return count if count >= K_ANONYMITY_THRESHOLD else 0


async def get_company_competition(
    db: AsyncSession,
    company_id: UUID,
    *,
    include_private: bool = False,
) -> int:
    """Count unique users who have activity for a given company (k-anonymized).

    Args:
        db: Database session.
        company_id: Target company UUID.
        include_private: If True, include private events.

    Returns:
        K-anonymized competitor count (0 if < 3).
    """
    query = select(func.count(func.distinct(ActivityEvent.user_id))).where(
        ActivityEvent.company_id == company_id,
    )
    if not include_private:
        query = query.where(ActivityEvent.is_private == False)  # noqa: E712

    result = await db.execute(query)
    raw_count = result.scalar() or 0
    return _apply_k_anonymity(raw_count)


async def get_company_signal(
    db: AsyncSession,
    company_id: UUID,
) -> CompanySignal | None:
    """Get the latest company signal for a given company."""
    result = await db.execute(
        select(CompanySignal)
        .where(CompanySignal.company_id == company_id)
        .order_by(CompanySignal.last_updated.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_company_signal_timeline(
    db: AsyncSession,
    company_id: UUID,
    days: int = 30,
) -> Sequence[CompanySignal]:
    """Get signal history for a company over the given number of days."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(CompanySignal)
        .where(
            CompanySignal.company_id == company_id,
            CompanySignal.last_updated >= cutoff,
        )
        .order_by(CompanySignal.last_updated.asc())
    )
    return result.scalars().all()


async def get_heatmap(
    db: AsyncSession,
    *,
    min_count: int = K_ANONYMITY_THRESHOLD,
    include_private: bool = False,
) -> list[dict]:
    """Get all companies with activity counts (k-anonymized heatmap).

    Returns companies where the anonymized count meets the minimum threshold.
    """
    query: Select = select(
        ActivityEvent.company_id,
        func.count(func.distinct(ActivityEvent.user_id)).label("competitor_count"),
    )
    if not include_private:
        query = query.where(ActivityEvent.is_private == False)  # noqa: E712

    query = query.group_by(ActivityEvent.company_id).having(
        func.count(func.distinct(ActivityEvent.user_id)) >= min_count
    )

    result = await db.execute(query)
    rows = result.all()

    # Get company names from latest signals
    items = []
    for row in rows:
        signal = await get_company_signal(db, row.company_id)
        items.append({
            "company_id": row.company_id,
            "company_name": signal.company_name if signal else "Unknown",
            "competitor_count": row.competitor_count,
            "trend": signal.trend if signal else "stable",
        })
    return items


async def get_alternative_recommendations(
    db: AsyncSession,
    limit: int = 5,
) -> list[dict]:
    """Find companies with lower competition (good alternatives to target).

    Returns companies with the fewest competitors that still have some
    signal activity, prioritizing those with rising trends.
    """
    result = await db.execute(
        select(CompanySignal)
        .where(CompanySignal.competitor_count < K_ANONYMITY_THRESHOLD * 3)
        .order_by(CompanySignal.competitor_count.asc(), CompanySignal.trend.desc())
        .limit(limit)
    )
    signals = result.scalars().all()

    recommendations = []
    for signal in signals:
        if signal.competitor_count > 0:
            rationale = (
                f"Only {signal.competitor_count} competitor(s) detected — "
                f"lower than average, trend: {signal.trend}"
            )
        else:
            rationale = (
                f"No significant competitor activity detected — "
                f"early opportunity, trend: {signal.trend}"
            )
        recommendations.append({
            "company_id": signal.company_id,
            "company_name": signal.company_name,
            "competitor_count": signal.competitor_count,
            "rationale": rationale,
        })
    return recommendations


async def add_to_watchlist(
    db: AsyncSession,
    user_id: UUID,
    company_id: UUID,
    company_name: str,
    notify_on_change: bool = True,
) -> CompanyWatchlist:
    """Add a company to the user's watchlist."""
    watchlist_entry = CompanyWatchlist(
        user_id=user_id,
        company_id=company_id,
        company_name=company_name,
        notify_on_change=notify_on_change,
    )
    db.add(watchlist_entry)
    await db.commit()
    await db.refresh(watchlist_entry)
    return watchlist_entry


async def remove_from_watchlist(
    db: AsyncSession,
    user_id: UUID,
    watchlist_id: UUID,
) -> bool:
    """Remove a company from the user's watchlist.

    Returns True if deleted, False if not found.
    """
    result = await db.execute(
        select(CompanyWatchlist).where(
            CompanyWatchlist.id == watchlist_id,
            CompanyWatchlist.user_id == user_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return False
    await db.delete(entry)
    await db.commit()
    return True


async def get_user_watchlist(
    db: AsyncSession,
    user_id: UUID,
) -> Sequence[CompanyWatchlist]:
    """Get all watchlist entries for a user."""
    result = await db.execute(
        select(CompanyWatchlist)
        .where(CompanyWatchlist.user_id == user_id)
        .order_by(CompanyWatchlist.created_at.desc())
    )
    return result.scalars().all()


async def log_activity_event(
    db: AsyncSession,
    user_id: UUID,
    company_id: UUID,
    activity_type: str,
    is_private: bool = False,
) -> ActivityEvent:
    """Log a user activity event targeting a company."""
    event = ActivityEvent(
        user_id=user_id,
        company_id=company_id,
        activity_type=activity_type,
        is_private=is_private,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def generate_report(
    db: AsyncSession,
    user_id: UUID,
) -> dict:
    """Generate a full insight report including signals, watchlist, and alternatives."""
    watchlist = await get_user_watchlist(db, user_id)
    alternatives = await get_alternative_recommendations(db)
    heatmap = await get_heatmap(db)

    company_signals = []
    for item in heatmap:
        signal = await get_company_signal(db, item["company_id"])
        if signal:
            company_signals.append(signal)

    return {
        "generated_at": datetime.now(UTC),
        "company_signals": company_signals,
        "watchlist": list(watchlist),
        "alternatives": alternatives,
    }
