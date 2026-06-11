"""Billing routes — subscribe, portal, invoices, cancel, upgrade, downgrade."""
from __future__ import annotations

import logging
from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.api.deps import DbSession, get_current_user
from mandate_finder.config import settings
from mandate_finder.models.invoice import Invoice
from mandate_finder.models.subscription import Subscription
from mandate_finder.models.user import User
from mandate_finder.schemas.billing import (
    BillingPortalResponse,
    CancelResponse,
    ChangePlanRequest,
    ChangePlanResponse,
    InvoiceResponse,
    PlanResponse,
    SubscribeRequest,
    SubscribeResponse,
    SubscriptionResponse,
)
from mandate_finder.services.billing_service import (
    StripeClient,
    ensure_default_plans,
    get_active_plans,
    get_plan_by_id,
    tier_is_downgrade,
    tier_is_upgrade,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


async def _current_user_id(
    db: AsyncSession, token_user: dict
) -> UUID:
    result = await db.execute(
        select(User).where(User.propelauth_user_id == token_user["user_id"])
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user.id


def _get_stripe_client() -> StripeClient:
    return StripeClient()


async def _get_or_create_subscription(
    db: AsyncSession, user_id: UUID
) -> Subscription | None:
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status.in_(["active", "past_due"]),
        )
    )
    return result.scalar_one_or_none()


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    db: DbSession,
) -> list[PlanResponse]:
    """List available subscription plans."""
    await ensure_default_plans(db)
    plans = await get_active_plans(db)
    return [PlanResponse.model_validate(p) for p in plans]


@router.get("/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(
    db: DbSession,
    current_user: dict = Depends(get_current_user),
) -> SubscriptionResponse | None:
    """Get current user's subscription."""
    user_id = await _current_user_id(db, current_user)
    sub = await _get_or_create_subscription(db, user_id)
    if not sub:
        return None

    plan = await get_plan_by_id(db, sub.plan_id)
    return SubscriptionResponse(
        id=sub.id,
        plan_id=sub.plan_id,
        plan_name=plan.name if plan else None,
        status=sub.status,
        trial_end_at=sub.trial_end_at,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        canceled_at=sub.canceled_at,
    )


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    data: SubscribeRequest,
    db: DbSession,
    current_user: dict = Depends(get_current_user),
) -> SubscribeResponse:
    """Create a new subscription with free trial."""
    user_id = await _current_user_id(db, current_user)
    existing = await _get_or_create_subscription(db, user_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has an active subscription",
        )

    plan = await get_plan_by_id(db, data.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    stripe = StripeClient()
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    customer_id = await stripe.find_or_create_customer(user)

    # Map plan tier to Stripe price ID if configured
    price_id = settings.stripe_price_ids.get(plan.tier, "")
    trial_days = settings.stripe_trial_days

    stripe_sub = await stripe.create_subscription(customer_id, price_id, trial_days)

    trial_end = None
    if stripe_sub.get("trial_end"):
        from datetime import datetime

        trial_end = datetime.fromtimestamp(stripe_sub["trial_end"], tz=UTC)

    period_start = None
    period_end = None
    if stripe_sub.get("current_period_start"):
        from datetime import datetime

        period_start = datetime.fromtimestamp(
            stripe_sub["current_period_start"], tz=UTC
        )
    if stripe_sub.get("current_period_end"):
        from datetime import datetime

        period_end = datetime.fromtimestamp(
            stripe_sub["current_period_end"], tz=UTC
        )

    subscription = Subscription(
        user_id=user_id,
        plan_id=plan.id,
        stripe_subscription_id=stripe_sub["id"],
        status=stripe_sub.get("status", "active"),
        trial_end_at=trial_end,
        current_period_start=period_start,
        current_period_end=period_end,
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)

    client_secret = None
    latest_invoice = stripe_sub.get("latest_invoice")
    if latest_invoice:
        payment_intent = latest_invoice.get("payment_intent")
        if payment_intent:
            client_secret = payment_intent.get("client_secret")

    return SubscribeResponse(
        subscription_id=subscription.id,
        status=subscription.status,
        trial_end_at=subscription.trial_end_at,
        client_secret=client_secret,
    )


@router.post("/portal", response_model=BillingPortalResponse)
async def billing_portal(
    db: DbSession,
    current_user: dict = Depends(get_current_user),
) -> BillingPortalResponse:
    """Get Stripe Customer Portal URL."""
    user_id = await _current_user_id(db, current_user)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    stripe = StripeClient()
    customer_id = await stripe.find_or_create_customer(user)
    url = await stripe.create_portal_session(customer_id)
    return BillingPortalResponse(url=url)


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    db: DbSession,
    current_user: dict = Depends(get_current_user),
) -> list[InvoiceResponse]:
    """List invoices for the current user."""
    user_id = await _current_user_id(db, current_user)
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    subs = result.scalars().all()
    if not subs:
        return []

    sub_ids = [s.id for s in subs]
    invoice_result = await db.execute(
        select(Invoice)
        .where(Invoice.subscription_id.in_(sub_ids))
        .order_by(Invoice.created_at.desc())
    )
    invoices = invoice_result.scalars().all()
    return [InvoiceResponse.model_validate(inv) for inv in invoices]


@router.post("/cancel", response_model=CancelResponse)
async def cancel_subscription(
    db: DbSession,
    current_user: dict = Depends(get_current_user),
) -> CancelResponse:
    """Cancel the current subscription."""
    user_id = await _current_user_id(db, current_user)
    sub = await _get_or_create_subscription(db, user_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )

    if sub.stripe_subscription_id:
        stripe = StripeClient()
        await stripe.cancel_subscription(sub.stripe_subscription_id)

    from datetime import datetime

    sub.status = "canceled"
    sub.canceled_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(sub)

    return CancelResponse(
        subscription_id=sub.id,
        status=sub.status,
        canceled_at=sub.canceled_at,
    )


@router.post("/upgrade", response_model=ChangePlanResponse)
async def upgrade_plan(
    data: ChangePlanRequest,
    db: DbSession,
    current_user: dict = Depends(get_current_user),
) -> ChangePlanResponse:
    """Upgrade to a higher-tier plan."""
    user_id = await _current_user_id(db, current_user)
    sub = await _get_or_create_subscription(db, user_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )

    current_plan = await get_plan_by_id(db, sub.plan_id)
    new_plan = await get_plan_by_id(db, data.plan_id)
    if not current_plan or not new_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    if not tier_is_upgrade(current_plan.tier, new_plan.tier):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not an upgrade. Use /billing/downgrade for downgrades.",
        )

    if sub.stripe_subscription_id:
        stripe = StripeClient()
        price_id = settings.stripe_price_ids.get(new_plan.tier, "")
        await stripe.update_subscription_plan(sub.stripe_subscription_id, price_id)

    sub.plan_id = new_plan.id
    await db.commit()
    await db.refresh(sub)

    return ChangePlanResponse(
        subscription_id=sub.id,
        status=sub.status,
        plan_id=new_plan.id,
        plan_name=new_plan.name,
    )


@router.post("/downgrade", response_model=ChangePlanResponse)
async def downgrade_plan(
    data: ChangePlanRequest,
    db: DbSession,
    current_user: dict = Depends(get_current_user),
) -> ChangePlanResponse:
    """Downgrade to a lower-tier plan at period end."""
    user_id = await _current_user_id(db, current_user)
    sub = await _get_or_create_subscription(db, user_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )

    current_plan = await get_plan_by_id(db, sub.plan_id)
    new_plan = await get_plan_by_id(db, data.plan_id)
    if not current_plan or not new_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    if not tier_is_downgrade(current_plan.tier, new_plan.tier):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not a downgrade. Use /billing/upgrade for upgrades.",
        )

    if sub.stripe_subscription_id:
        stripe = StripeClient()
        price_id = settings.stripe_price_ids.get(new_plan.tier, "")
        # Downgrade takes effect at period end
        await stripe.update_subscription_plan(sub.stripe_subscription_id, price_id)

    sub.plan_id = new_plan.id
    await db.commit()
    await db.refresh(sub)

    return ChangePlanResponse(
        subscription_id=sub.id,
        status=sub.status,
        plan_id=new_plan.id,
        plan_name=new_plan.name,
    )
