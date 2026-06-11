"""Batch competition signal aggregation worker.

Runs every 6 hours to:
1. Compute competitor counts per company from activity_events
2. Update company_signals with current counts and trends
3. Apply k-anonymity (hide counts < 3)
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.activity_event import ActivityEvent
from mandate_finder.models.company_signal import CompanySignal

logger = logging.getLogger(__name__)

K_ANONYMITY_THRESHOLD = 3


def _compute_trend(
    current_count: int,
    previous_count: int,
) -> str:
    """Compute trend label based on count change."""
    if current_count > previous_count:
        return "rising"
    elif current_count < previous_count:
        return "declining"
    return "stable"


async def aggregate_signals(db: AsyncSession) -> list[CompanySignal]:
    """Aggregate activity events into company signals.

    1. Count distinct users per company (excluding private events).
    2. Upsert into company_signals table.
    3. Compute trend by comparing with previous signal.

    Returns:
        List of updated CompanySignal records.
    """
    # Get current raw counts per company (excluding private events)
    raw_counts_query = select(
        ActivityEvent.company_id,
        func.count(func.distinct(ActivityEvent.user_id)).label("competitor_count"),
    ).where(
        ActivityEvent.is_private == False,  # noqa: E712
    ).group_by(ActivityEvent.company_id)

    raw_result = await db.execute(raw_counts_query)
    raw_counts = {row.company_id: row.competitor_count for row in raw_result.all()}

    if not raw_counts:
        logger.info("No activity events to aggregate")
        return []

    # Get existing signals for trend comparison
    existing = await db.execute(
        select(CompanySignal).where(
            CompanySignal.company_id.in_(raw_counts.keys())
        )
    )
    existing_signals: dict[UUID, CompanySignal] = {
        s.company_id: s for s in existing.scalars().all()
    }

    updated_signals: list[CompanySignal] = []
    now = datetime.now(UTC)

    for company_id, raw_count in raw_counts.items():
        previous_count = existing_signals.get(company_id)
        prev_count_value = previous_count.competitor_count if previous_count else 0

        trend = _compute_trend(raw_count, prev_count_value)
        display_count = raw_count if raw_count >= K_ANONYMITY_THRESHOLD else 0

        if previous_count:
            previous_count.competitor_count = display_count
            previous_count.trend = trend
            previous_count.last_updated = now
            updated_signals.append(previous_count)
        else:
            # Get a company name from any activity event
            name_result = await db.execute(
                select(ActivityEvent).where(
                    ActivityEvent.company_id == company_id
                ).limit(1)
            )
            event = name_result.scalar_one_or_none()
            company_name = (
                f"Company-{str(company_id)[:8]}"
                if not event
                else "Unknown"
            )

            signal = CompanySignal(
                company_id=company_id,
                company_name=company_name,
                competitor_count=display_count,
                trend=trend,
                last_updated=now,
            )
            db.add(signal)
            updated_signals.append(signal)

    await db.commit()

    for signal in updated_signals:
        await db.refresh(signal)

    logger.info(
        "Aggregated %d company signals (k=%d threshold)",
        len(updated_signals),
        K_ANONYMITY_THRESHOLD,
    )
    return updated_signals


async def run_signal_aggregation(db: AsyncSession) -> dict:
    """Run the full signal aggregation workflow.

    This is the main entry point called by the scheduler every 6 hours.

    Returns:
        Summary dict with counts.
    """
    signals = await aggregate_signals(db)
    return {
        "status": "completed",
        "signals_updated": len(signals),
        "timestamp": datetime.now(UTC).isoformat(),
    }
