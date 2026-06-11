from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session
from src.models.billing import Plan, PlanTier, Subscription, SubscriptionStatus


class SubscriptionService:

    @staticmethod
    async def get_active_subscription(
        user_id: uuid.UUID,
        session: AsyncSession | None = None,
    ) -> Subscription | None:
        async def _query(s: AsyncSession) -> Subscription | None:
            stmt = (
                select(Subscription)
                .where(
                    Subscription.user_id == user_id,
                    Subscription.status.in_([
                        SubscriptionStatus.trialing,
                        SubscriptionStatus.active,
                        SubscriptionStatus.past_due,
                    ]),
                )
                .order_by(Subscription.created_at.desc())
                .limit(1)
            )
            result = await s.execute(stmt)
            return result.scalar_one_or_none()

        if session:
            return await _query(session)
        async with async_session() as s:
            return await _query(s)

    @staticmethod
    async def get_plan_by_tier(
        tier: PlanTier,
        session: AsyncSession | None = None,
    ) -> Plan | None:
        async def _query(s: AsyncSession) -> Plan | None:
            stmt = select(Plan).where(Plan.tier == tier.value)
            result = await s.execute(stmt)
            return result.scalar_one_or_none()

        if session:
            return await _query(session)
        async with async_session() as s:
            return await _query(s)

    @staticmethod
    async def create_or_update_subscription(
        user_id: uuid.UUID,
        plan_tier: PlanTier,
        stripe_subscription_id: str,
        stripe_customer_id: str,
        status: SubscriptionStatus,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        trial_end: datetime | None = None,
        session: AsyncSession | None = None,
    ) -> Subscription:
        async def _upsert(s: AsyncSession) -> Subscription:
            stmt = (
                select(Subscription)
                .where(Subscription.user_id == user_id)
                .order_by(Subscription.created_at.desc())
                .limit(1)
            )
            result = await s.execute(stmt)
            sub = result.scalar_one_or_none()

            plan = await SubscriptionService.get_plan_by_tier(plan_tier, session=s)
            if not plan:
                msg = f"Plan not found for tier: {plan_tier.value}"
                raise ValueError(msg)

            if sub:
                sub.plan_id = plan.id
                sub.stripe_subscription_id = stripe_subscription_id
                sub.stripe_customer_id = stripe_customer_id
                sub.status = status
                sub.current_period_start = period_start
                sub.current_period_end = period_end
                sub.trial_end = trial_end
                if status in (
                    SubscriptionStatus.canceled,
                    SubscriptionStatus.suspended,
                ):
                    sub.ended_at = datetime.now(UTC)
            else:
                sub = Subscription(
                    user_id=user_id,
                    plan_id=plan.id,
                    stripe_subscription_id=stripe_subscription_id,
                    stripe_customer_id=stripe_customer_id,
                    status=status,
                    current_period_start=period_start,
                    current_period_end=period_end,
                    trial_end=trial_end,
                )
                s.add(sub)

            await s.commit()
            await s.refresh(sub)
            return sub

        if session:
            return await _upsert(session)
        async with async_session() as s:
            return await _upsert(s)
