"""Billing service — Stripe integration, plan management, VAT handling."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.config import settings
from mandate_finder.models.plan import Plan, PlanTier
from mandate_finder.models.user import User

logger = logging.getLogger(__name__)

# ── Default plans ──────────────────────────────────────────────────────────

DEFAULT_PLANS: list[dict] = [
    {
        "name": "Solo",
        "tier": PlanTier.SOLO.value,
        "price_monthly_eur": 4900,  # €49.00 in cents
        "features": {
            "max_searches": 50,
            "max_team_members": 1,
            "crm_integrations": False,
            "api_access": False,
            "export_csv": True,
            "priority_support": False,
        },
    },
    {
        "name": "Professional",
        "tier": PlanTier.PROFESSIONAL.value,
        "price_monthly_eur": 19900,  # €199.00 in cents
        "features": {
            "max_searches": 500,
            "max_team_members": 5,
            "crm_integrations": True,
            "api_access": True,
            "export_csv": True,
            "priority_support": False,
        },
    },
    {
        "name": "Agency",
        "tier": PlanTier.AGENCY.value,
        "price_monthly_eur": 49900,  # €499.00 in cents
        "features": {
            "max_searches": 5000,
            "max_team_members": 50,
            "crm_integrations": True,
            "api_access": True,
            "export_csv": True,
            "priority_support": True,
        },
    },
]

# ── VAT helpers ────────────────────────────────────────────────────────────

GERMAN_VAT_PERCENTAGE = 19


def calculate_vat(amount_cents: int, is_b2b: bool = False) -> tuple[int, int]:
    """Return (vat_amount_cents, total_cents).

    B2B: reverse charge — 0% VAT applies (German UStG §13b).
    B2C: 19% German VAT.
    """
    if is_b2b:
        return 0, amount_cents
    vat = round(amount_cents * GERMAN_VAT_PERCENTAGE / 100)
    return vat, amount_cents + vat


def get_vat_percentage(is_b2b: bool = False) -> int:
    """Return the applicable VAT percentage."""
    return 0 if is_b2b else GERMAN_VAT_PERCENTAGE


# ── Stripe client wrapper ─────────────────────────────────────────────────


class StripeClient:
    """Minimal Stripe integration.

    In dev mode (no API key set) all operations are simulated.
    Production usage requires ``stripe`` pypi package and a configured key.
    """

    def __init__(self) -> None:
        self.api_key = settings.stripe_api_key
        self._dev_mode = not bool(self.api_key.strip())

    # -- helpers -----------------------------------------------------------

    def _import_stripe(self):
        import stripe  # type: ignore[import-untyped]

        stripe.api_key = self.api_key
        return stripe

    # -- customers ---------------------------------------------------------

    async def find_or_create_customer(self, user: User) -> str:
        """Return the Stripe customer ID for *user*."""
        if self._dev_mode:
            return f"cus_dev_{user.id}"

        stripe = self._import_stripe()

        if user.stripe_customer_id:
            return user.stripe_customer_id

        customer = stripe.Customer.create(
            email=user.email,
            name=user.username,
            metadata={"user_id": str(user.id)},
        )
        return customer["id"]

    # -- subscriptions -----------------------------------------------------

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        trial_days: int = 14,
    ) -> dict:
        """Create a new Stripe subscription and return its dict."""
        if self._dev_mode:
            return {
                "id": f"sub_dev_{UUID(int=0)}",
                "status": "active",
                "current_period_start": int(datetime.now(UTC).timestamp()),
                "current_period_end": int(
                    (datetime.now(UTC) + timedelta(days=30)).timestamp()
                ),
                "latest_invoice": {
                    "payment_intent": {"client_secret": None},
                },
            }

        stripe = self._import_stripe()
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id}],
            trial_period_days=trial_days,
            payment_behavior="default_incomplete",
            expand=["latest_invoice.payment_intent"],
        )
        return subscription

    async def cancel_subscription(self, stripe_subscription_id: str) -> dict:
        """Cancel a Stripe subscription."""
        if self._dev_mode:
            return {"id": stripe_subscription_id, "status": "canceled"}

        stripe = self._import_stripe()
        return stripe.Subscription.cancel(stripe_subscription_id)

    async def update_subscription_plan(
        self, stripe_subscription_id: str, new_price_id: str
    ) -> dict:
        """Change the price on an existing subscription."""
        if self._dev_mode:
            return {"id": stripe_subscription_id, "status": "active"}

        stripe = self._import_stripe()
        sub = stripe.Subscription.retrieve(stripe_subscription_id)
        subscription_item_id = sub["items"]["data"][0]["id"]
        return stripe.Subscription.modify(
            stripe_subscription_id,
            items=[{"id": subscription_item_id, "price": new_price_id}],
            proration_behavior="always_invoice",
        )

    # -- billing portal ----------------------------------------------------

    async def create_portal_session(self, customer_id: str) -> str:
        """Return a Stripe Customer Portal URL."""
        if self._dev_mode:
            return f"https://dev-billing.example.com/portal/{customer_id}"

        stripe = self._import_stripe()
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=settings.stripe_return_url,
        )
        return session["url"]

    # -- invoices / receipts -----------------------------------------------

    async def retrieve_invoice(self, stripe_invoice_id: str) -> dict | None:
        if self._dev_mode:
            return None
        stripe = self._import_stripe()
        return stripe.Invoice.retrieve(stripe_invoice_id)

    # -- webhook event helpers ---------------------------------------------

    def parse_webhook_event(self, payload: bytes, sig_header: str) -> dict:
        """Verify and parse a Stripe webhook event.

        In dev mode, parse the JSON payload directly without verification.
        """
        if self._dev_mode:
            import json

            return json.loads(payload)

        stripe = self._import_stripe()
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )


# ── Service layer ─────────────────────────────────────────────────────────


async def ensure_default_plans(db: AsyncSession) -> list[Plan]:
    """Create default plans if none exist. Returns plan list."""
    result = await db.execute(select(Plan).limit(1))
    if result.scalar_one_or_none():
        result = await db.execute(select(Plan).where(Plan.is_active.is_(True)))
        return list(result.scalars().all())

    plans = []
    for data in DEFAULT_PLANS:
        plan = Plan(**data)
        db.add(plan)
        plans.append(plan)
    await db.commit()
    for plan in plans:
        await db.refresh(plan)
    return plans


async def get_plan_by_tier(db: AsyncSession, tier: str) -> Plan | None:
    result = await db.execute(
        select(Plan).where(Plan.tier == tier, Plan.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def get_plan_by_id(db: AsyncSession, plan_id: UUID) -> Plan | None:
    result = await db.execute(
        select(Plan).where(Plan.id == plan_id, Plan.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def get_active_plans(db: AsyncSession) -> list[Plan]:
    result = await db.execute(select(Plan).where(Plan.is_active.is_(True)))
    return list(result.scalars().all())


SUBSCRIPTION_TIER_ORDER: dict[str, int] = {
    PlanTier.SOLO.value: 1,
    PlanTier.PROFESSIONAL.value: 2,
    PlanTier.AGENCY.value: 3,
}


def tier_is_upgrade(current_tier: str, new_tier: str) -> bool:
    return SUBSCRIPTION_TIER_ORDER.get(new_tier, 0) > SUBSCRIPTION_TIER_ORDER.get(
        current_tier, 0
    )


def tier_is_downgrade(current_tier: str, new_tier: str) -> bool:
    return SUBSCRIPTION_TIER_ORDER.get(new_tier, 0) < SUBSCRIPTION_TIER_ORDER.get(
        current_tier, 0
    )


# ── Feature gating ────────────────────────────────────────────────────────


FEATURE_TIER_MAP: dict[str, str] = {
    "max_searches": PlanTier.SOLO.value,
    "max_team_members": PlanTier.SOLO.value,
    "crm_integrations": PlanTier.PROFESSIONAL.value,
    "api_access": PlanTier.PROFESSIONAL.value,
    "export_csv": PlanTier.SOLO.value,
    "priority_support": PlanTier.AGENCY.value,
}


def requires_feature(feature: str) -> str:
    """Return the minimum tier required for *feature*."""
    return FEATURE_TIER_MAP.get(feature, PlanTier.SOLO.value)


def user_has_feature(user_tier: str, feature: str) -> bool:
    """Check if a user's plan tier has access to *feature*."""
    required = requires_feature(feature)
    return (
        SUBSCRIPTION_TIER_ORDER.get(user_tier, 0)
        >= SUBSCRIPTION_TIER_ORDER.get(required, 0)
    )
