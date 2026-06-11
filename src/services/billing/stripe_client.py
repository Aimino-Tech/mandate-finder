from __future__ import annotations

import logging
import uuid
from typing import Any

import stripe

from src.config import settings
from src.models.billing import PlanTier, SubscriptionStatus
from src.services.billing.plans import ALL_PLANS, get_plan_config

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_secret_key


def _get_price_id(tier: PlanTier) -> str:
    plan = get_plan_config(tier.value)
    if not plan:
        msg = f"Unknown plan tier: {tier}"
        raise ValueError(msg)
    env_var = plan.stripe_price_id_env
    price_id = getattr(settings, env_var.lower(), "")
    if not price_id:
        msg = f"Stripe price ID not configured for {tier.value} (env: {env_var})"
        raise ValueError(msg)
    return price_id


async def create_stripe_customer(
    email: str,
    name: str | None = None,
    metadata: dict[str, str] | None = None,
) -> stripe.Customer:
    return stripe.Customer.create(
        email=email,
        name=name,
        metadata=metadata or {},
    )


async def create_checkout_session(
    user_id: uuid.UUID,
    email: str,
    tier: PlanTier,
    *,
    success_url: str,
    cancel_url: str,
    trial_days: int = 14,
    metadata: dict[str, str] | None = None,
    coupon_code: str | None = None,
) -> stripe.checkout.Session:
    price_id = _get_price_id(tier)
    line_items = [{"price": price_id, "quantity": 1}]

    session_params: dict[str, Any] = {
        "mode": "subscription",
        "customer_email": email,
        "line_items": line_items,
        "subscription_data": {"trial_period_days": trial_days},
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {
            "user_id": str(user_id),
            "plan_tier": tier.value,
            **(metadata or {}),
        },
    }

    if coupon_code:
        promotion_codes = stripe.PromotionCode.list(
            code=coupon_code, active=True, limit=1
        )
        if promotion_codes.data:
            session_params["discounts"] = [
                {"promotion_code": promotion_codes.data[0].id}
            ]

    return stripe.checkout.Session.create(**session_params)


async def create_billing_portal_session(
    stripe_customer_id: str,
    return_url: str,
) -> stripe.billing_portal.Session:
    return stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url,
    )


async def get_subscription(
    stripe_subscription_id: str,
) -> stripe.Subscription:
    return stripe.Subscription.retrieve(stripe_subscription_id)


async def update_subscription_plan(
    stripe_subscription_id: str,
    new_tier: PlanTier,
    *,
    proration_behavior: str = "create_prorations",
) -> stripe.Subscription:
    price_id = _get_price_id(new_tier)
    sub = stripe.Subscription.retrieve(stripe_subscription_id)

    return stripe.Subscription.modify(
        stripe_subscription_id,
        items=[
            {
                "id": sub["items"]["data"][0].id,
                "price": price_id,
            }
        ],
        proration_behavior=proration_behavior,
        metadata={"plan_tier": new_tier.value},
    )


async def cancel_subscription(
    stripe_subscription_id: str,
    *,
    cancel_at_period_end: bool = True,
) -> stripe.Subscription:
    if cancel_at_period_end:
        return stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=True,
        )
    return stripe.Subscription.cancel(stripe_subscription_id)


async def reactivate_subscription(
    stripe_subscription_id: str,
) -> stripe.Subscription:
    return stripe.Subscription.modify(
        stripe_subscription_id,
        cancel_at_period_end=False,
    )


async def list_invoices(
    stripe_customer_id: str,
    limit: int = 50,
) -> list[stripe.Invoice]:
    return stripe.Invoice.list(
        customer=stripe_customer_id,
        limit=limit,
    )


def parse_subscription_status(stripe_status: str) -> SubscriptionStatus:
    mapping = {
        "trialing": SubscriptionStatus.trialing,
        "active": SubscriptionStatus.active,
        "past_due": SubscriptionStatus.past_due,
        "canceled": SubscriptionStatus.canceled,
        "incomplete": SubscriptionStatus.incomplete,
        "incomplete_expired": SubscriptionStatus.incomplete_expired,
        "paused": SubscriptionStatus.paused,
        "unpaid": SubscriptionStatus.unpaid,
    }
    return mapping.get(stripe_status, SubscriptionStatus.incomplete)


def tier_from_price_id(price_id: str) -> PlanTier | None:
    for tier, plan in ALL_PLANS.items():
        env_var = plan.stripe_price_id_env.lower()
        configured_id = getattr(settings, env_var, "")
        if configured_id and configured_id == price_id:
            return tier
    return None


async def get_upcoming_invoice(
    stripe_customer_id: str,
    subscription_id: str,
    *,
    new_tier: PlanTier | None = None,
) -> stripe.UpcomingInvoice:
    params: dict[str, Any] = {
        "customer": stripe_customer_id,
        "subscription": subscription_id,
    }
    if new_tier:
        sub = stripe.Subscription.retrieve(subscription_id)
        new_price_id = _get_price_id(new_tier)
        params["subscription_items"] = [
            {
                "id": sub["items"]["data"][0].id,
                "price": new_price_id,
            }
        ]
    return stripe.Invoice.upcoming(**params)
