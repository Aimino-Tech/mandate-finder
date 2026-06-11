from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from src.database import async_session
from src.models.billing import Subscription, SubscriptionStatus

logger = logging.getLogger(__name__)


class DunningService:
    RETRY_INTERVALS = [
        timedelta(days=1),
        timedelta(days=3),
        timedelta(days=7),
    ]
    MAX_RETRIES = 3

    @staticmethod
    async def get_past_due_subscriptions() -> list[Subscription]:
        async with async_session() as session:
            stmt = (
                select(Subscription)
                .where(Subscription.status == SubscriptionStatus.past_due)
                .order_by(Subscription.updated_at.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @staticmethod
    async def get_retry_count(subscription: Subscription) -> int:
        async with async_session() as session:
            from src.models.billing import SubscriptionEvent

            stmt = (
                select(SubscriptionEvent)
                .where(
                    SubscriptionEvent.subscription_id == subscription.id,
                    SubscriptionEvent.event_type == "dunning_retry",
                )
                .order_by(SubscriptionEvent.created_at.desc())
            )
            result = await session.execute(stmt)
            return len(result.scalars().all())

    @staticmethod
    async def record_dunning_event(
        subscription_id: uuid.UUID,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        from src.models.billing import SubscriptionEvent

        async with async_session() as session:
            event = SubscriptionEvent(
                subscription_id=subscription_id,
                event_type=event_type,
                data=data,
            )
            session.add(event)
            await session.commit()

    @staticmethod
    async def send_dunning_email(
        subscription: Subscription,
        retry_count: int,
    ) -> None:
        logger.info(
            "Sending dunning email for sub %s (user %s, attempt %d/%d)",
            subscription.id,
            subscription.user_id,
            retry_count + 1,
            DunningService.MAX_RETRIES,
        )

    @staticmethod
    async def suspend_subscription(subscription: Subscription) -> None:
        async with async_session() as session:
            stmt = select(Subscription).where(
                Subscription.id == subscription.id
            )
            result = await session.execute(stmt)
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = SubscriptionStatus.suspended
                sub.ended_at = datetime.now(UTC)
                await session.commit()

        logger.warning(
            "Subscription %s suspended for user %s",
            subscription.id,
            subscription.user_id,
        )


async def process_dunning() -> None:
    past_due = await DunningService.get_past_due_subscriptions()

    for sub in past_due:
        retry_count = await DunningService.get_retry_count(sub)

        if retry_count >= DunningService.MAX_RETRIES:
            await DunningService.record_dunning_event(
                sub.id, "dunning_suspend", {"retry_count": retry_count}
            )
            await DunningService.suspend_subscription(sub)
            continue

        last_event_time = sub.updated_at
        expected_interval = DunningService.RETRY_INTERVALS[retry_count]

        if datetime.now(UTC) - last_event_time >= expected_interval:
            await DunningService.send_dunning_email(sub, retry_count)

            await DunningService.record_dunning_event(
                sub.id,
                "dunning_retry",
                {"attempt": retry_count + 1, "max_retries": DunningService.MAX_RETRIES},
            )

            logger.info(
                "Dunning retry %d/%d for subscription %s",
                retry_count + 1,
                DunningService.MAX_RETRIES,
                sub.id,
            )


scheduler = TaskiqScheduler(
    schedule_source=LabelScheduleSource(),
)
