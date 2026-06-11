"""Dunning worker — 3 retries over 7 days, then suspend."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.subscription import Subscription

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """Return a timezone-naive UTC datetime for DB comparison."""
    return datetime.now(UTC).replace(tzinfo=None)


async def process_dunning(db: AsyncSession) -> list[dict]:
    """Process payment-dunning for past_due subscriptions.

    Schedule: 3 retry attempts over ~7 days.

      Retry 1: immediately (day 0)
      Retry 2: day 2
      Retry 3: day 5
      Suspend: day 7

    Returns a list of action records for audit/monitoring.
    """
    actions: list[dict] = []

    result = await db.execute(
        select(Subscription).where(Subscription.status == "past_due")
    )
    past_due_subs = result.scalars().all()

    now = _now()

    for sub in past_due_subs:
        updated = sub.updated_at or sub.created_at
        if updated is None:
            continue
        # Ensure both naive for comparison
        if updated.tzinfo is not None:
            updated = updated.replace(tzinfo=None)
        days_since_update = (now - updated).total_seconds() / 86400

        if days_since_update >= 7:
            # Suspend after 7 days of failed payment
            old_status = sub.status
            sub.status = "expired"
            await db.commit()
            logger.warning(
                "Subscription %s suspended after dunning period (status: %s -> expired)",
                sub.id,
                old_status,
            )
            actions.append(
                {
                    "subscription_id": str(sub.id),
                    "action": "suspended",
                    "days_overdue": round(days_since_update, 1),
                }
            )
        else:
            # Determine retry number
            if days_since_update < 2:
                retry = 1
            elif days_since_update < 5:
                retry = 2
            else:
                retry = 3

            logger.info(
                "Subscription %s — dunning retry %d (%.1f days overdue)",
                sub.id,
                retry,
                days_since_update,
            )
            actions.append(
                {
                    "subscription_id": str(sub.id),
                    "action": f"retry_{retry}",
                    "days_overdue": round(days_since_update, 1),
                }
            )

    return actions
