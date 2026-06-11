"""Feature gating middleware — checks user plan tier against required feature."""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.api.deps import DbSession, get_current_user
from mandate_finder.models.plan import Plan
from mandate_finder.models.subscription import Subscription
from mandate_finder.models.user import User
from mandate_finder.services.billing_service import user_has_feature


async def _get_user_and_subscription(
    db: AsyncSession, token_user: dict
) -> tuple[User, str, str] | None:
    """Return (user, user_tier, sub_status) or None."""
    result = await db.execute(
        select(User).where(User.propelauth_user_id == token_user["user_id"])
    )
    user = result.scalar_one_or_none()
    if not user:
        return None

    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status.in_(["active", "past_due", "trialing"]),
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return user, "none", "none"

    plan_result = await db.execute(select(Plan).where(Plan.id == sub.plan_id))
    plan = plan_result.scalar_one_or_none()
    user_tier = plan.tier if plan else "none"
    return user, user_tier, sub.status


async def get_user_tier(
    db: DbSession, current_user: dict = Depends(get_current_user)
) -> str:
    """Return the current user's plan tier (or 'none')."""
    info = await _get_user_and_subscription(db, current_user)
    if info is None:
        return "none"
    _, tier, _ = info
    return tier


UserTier = Annotated[str, Depends(get_user_tier)]


def require_feature(feature: str) -> Callable[[UserTier], Any]:
    """Dependency factory — raise 403 if user's tier lacks *feature*."""

    async def _require(tier: UserTier) -> None:
        if tier == "none":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active subscription. Please subscribe to access this feature.",
            )
        if not user_has_feature(tier, feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your plan does not include '{feature}'. Please upgrade.",
            )

    return _require
