from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, status

from src.api.auth import UserInfo, get_current_user, parse_user_id
from src.models.billing import Feature, SubscriptionStatus
from src.services.billing.plans import get_plan_config, requires_feature
from src.services.billing.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


class FeatureGate:
    def __init__(self, required_feature: Feature):
        self.required_feature = required_feature

    async def __call__(
        self,
        user: UserInfo = Depends(get_current_user),
    ) -> None:
        user_id = parse_user_id(user)
        sub = await SubscriptionService.get_active_subscription(user_id)

        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active subscription found",
            )

        if sub.status == SubscriptionStatus.suspended:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Account suspended due to payment issues."
                    " Please update your payment method."
                ),
            )

        plan = get_plan_config(sub.plan.tier.value)
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid plan configuration",
            )

        if not requires_feature(self.required_feature, plan.tier):
            feature_name = self.required_feature.value.replace("_", " ").title()
            upgrade_tier = self._suggest_upgrade(plan.tier.value)

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Your current plan ({plan.name}) does not include "
                    f"'{feature_name}'. {upgrade_tier}"
                ),
            )

    def _suggest_upgrade(self, current_tier: str) -> str:
        from src.models.billing import PlanTier

        tiers = [PlanTier.solo, PlanTier.professional, PlanTier.agency]
        ordered = [t.value for t in tiers]
        try:
            idx = ordered.index(current_tier)
            if idx < len(ordered) - 1:
                return f"Upgrade to {ordered[idx + 1].title()} to unlock this feature."
            return "Contact support for more information."
        except ValueError:
            return ""


def require_feature(feature: Feature) -> Callable[..., Any]:
    return Depends(FeatureGate(feature))
