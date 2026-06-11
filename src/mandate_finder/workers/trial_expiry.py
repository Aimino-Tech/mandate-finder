"""Trial expiry worker — check trial status and notify at 7/3/1 days before."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.subscription import Subscription

logger = logging.getLogger(__name__)

NOTIFICATION_WINDOWS_DAYS = [7, 3, 1]


def _now() -> datetime:
    """Return a timezone-naive UTC datetime for DB comparison."""
    return datetime.now(UTC).replace(tzinfo=None)


async def check_trial_expiry(
    db: AsyncSession,
) -> list[dict]:
    """Check for expiring trials and return notification actions.

    Returns a list of dicts with user / subscription info for
    the notification dispatcher to act on.
    """
    now = _now()
    actions: list[dict] = []

    result = await db.execute(
        select(Subscription).where(
            Subscription.status == "trialing",
            Subscription.trial_end_at.isnot(None),
        )
    )
    trialing_subs = result.scalars().all()

    for sub in trialing_subs:
        if sub.trial_end_at is None:
            continue
        trial_end = sub.trial_end_at
        if trial_end.tzinfo is not None:
            trial_end = trial_end.replace(tzinfo=None)
        remaining = (trial_end - now).total_seconds() / 86400

        if remaining <= 0:
            # Trial expired — mark as active (if still trialing) or handle
            old_status = sub.status
            sub.status = "active"
            await db.commit()
            logger.info(
                "Trial expired for subscription %s (status: %s -> active)",
                sub.id,
                old_status,
            )
            actions.append(
                {
                    "subscription_id": str(sub.id),
                    "action": "trial_expired",
                    "days_remaining": 0,
                }
            )
        elif remaining <= 1:
            actions.append(
                {
                    "subscription_id": str(sub.id),
                    "action": "trial_ending_soon",
                    "days_remaining": 1,
                }
            )
        elif remaining <= 3:
            actions.append(
                {
                    "subscription_id": str(sub.id),
                    "action": "trial_ending_soon",
                    "days_remaining": 3,
                }
            )
        elif remaining <= 7:
            actions.append(
                {
                    "subscription_id": str(sub.id),
                    "action": "trial_ending_soon",
                    "days_remaining": 7,
                }
            )

    return actions
