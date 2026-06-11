from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import UserInfo, get_current_user, parse_user_id
from src.database import get_session
from src.models.billing import Invoice, PlanTier, SubscriptionStatus
from src.services.billing.plans import ALL_PLANS
from src.services.billing.stripe_client import (
    cancel_subscription as stripe_cancel_subscription,
)
from src.services.billing.stripe_client import (
    create_billing_portal_session as stripe_create_portal_session,
)
from src.services.billing.stripe_client import (
    create_checkout_session as stripe_create_checkout_session,
)
from src.services.billing.stripe_client import (
    get_subscription as stripe_get_subscription,
)
from src.services.billing.stripe_client import (
    reactivate_subscription as stripe_reactivate_subscription,
)
from src.services.billing.stripe_client import (
    update_subscription_plan as stripe_update_plan,
)
from src.services.billing.subscription_service import SubscriptionService

router = APIRouter(prefix="/api/billing", tags=["billing"])


class PlanResponse(BaseModel):
    tier: str
    name: str
    price_eur: float
    description: str
    features: list[str]
    max_team_members: int
    is_current: bool = False


class SubscriptionResponse(BaseModel):
    id: str
    plan_tier: str
    plan_name: str
    status: str
    current_period_start: str | None = None
    current_period_end: str | None = None
    trial_end: str | None = None
    canceled_at: str | None = None
    days_remaining: int | None = None


class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    status: str
    total_gross: str
    total_net: str
    vat_amount: str
    currency: str
    period_start: str | None = None
    period_end: str | None = None
    paid_at: str | None = None
    pdf_url: str | None = None


class CreateCheckoutRequest(BaseModel):
    tier: PlanTier
    success_url: str
    cancel_url: str
    coupon_code: str | None = None


class UpdatePlanRequest(BaseModel):
    tier: PlanTier


class BillingPortalRequest(BaseModel):
    return_url: str


class InvoiceDetailRequest(BaseModel):
    company_name: str | None = Field(None, max_length=255)
    company_vat_id: str | None = Field(None, max_length=50)
    company_address: str | None = Field(None, max_length=500)


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    user: UserInfo = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    user_id = parse_user_id(user)
    sub = await SubscriptionService.get_active_subscription(user_id, session=session)

    plans = []
    for tier, config in sorted(
        ALL_PLANS.items(), key=lambda x: x[1].sort_order
    ):
        is_current = sub is not None and sub.plan.tier == tier.value
        plans.append(
            PlanResponse(
                tier=tier.value,
                name=config.name,
                price_eur=config.price_eur,
                description=config.description,
                features=[f.value for f in config.features],
                max_team_members=config.max_team_members,
                is_current=is_current,
            )
        )
    return plans


@router.get("/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(
    user: UserInfo = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    user_id = parse_user_id(user)
    sub = await SubscriptionService.get_active_subscription(user_id, session=session)

    if sub is None:
        return None

    days_remaining = None
    if sub.current_period_end:
        delta = sub.current_period_end - datetime.now(timezone.UTC)
        days_remaining = delta.days

    return SubscriptionResponse(
        id=str(sub.id),
        plan_tier=sub.plan.tier,
        plan_name=sub.plan.name,
        status=sub.status.value,
        current_period_start=(
            sub.current_period_start.isoformat()
            if sub.current_period_start
            else None
        ),
        current_period_end=(
            sub.current_period_end.isoformat()
            if sub.current_period_end
            else None
        ),
        trial_end=sub.trial_end.isoformat() if sub.trial_end else None,
        canceled_at=sub.canceled_at.isoformat() if sub.canceled_at else None,
        days_remaining=days_remaining,
    )


@router.post("/checkout", status_code=status.HTTP_201_CREATED)
async def create_checkout(
    req: CreateCheckoutRequest,
    user: UserInfo = Depends(get_current_user),  # noqa: B008
):
    user_id = parse_user_id(user)

    session_data = await stripe_create_checkout_session(
        user_id=user_id,
        email=user.email,
        tier=req.tier,
        success_url=req.success_url,
        cancel_url=req.cancel_url,
        coupon_code=req.coupon_code,
    )

    return {"checkout_url": session_data.url, "session_id": session_data.id}


@router.post("/portal")
async def billing_portal(
    req: BillingPortalRequest,
    user: UserInfo = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    user_id = parse_user_id(user)
    sub = await SubscriptionService.get_active_subscription(user_id, session=session)

    if not sub or not sub.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription found",
        )

    portal = await stripe_create_portal_session(
        stripe_customer_id=sub.stripe_customer_id,
        return_url=req.return_url,
    )

    return {"url": portal.url}


@router.post("/upgrade")
async def upgrade_plan(
    req: UpdatePlanRequest,
    user: UserInfo = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    user_id = parse_user_id(user)
    sub = await SubscriptionService.get_active_subscription(user_id, session=session)

    if not sub or not sub.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to upgrade",
        )

    if sub.plan.tier == req.tier.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Already on {req.tier.value} plan",
        )

    tiers = [PlanTier.solo, PlanTier.professional, PlanTier.agency]
    current_idx = tiers.index(PlanTier(sub.plan.tier))
    target_idx = tiers.index(req.tier)
    if target_idx < current_idx:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use downgrade endpoint for downgrading",
        )

    await stripe_update_plan(sub.stripe_subscription_id, req.tier)
    return {"message": f"Upgrading to {req.tier.value}"}


@router.post("/downgrade")
async def downgrade_plan(
    req: UpdatePlanRequest,
    user: UserInfo = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    user_id = parse_user_id(user)
    sub = await SubscriptionService.get_active_subscription(user_id, session=session)

    if not sub or not sub.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to downgrade",
        )

    tiers = [PlanTier.solo, PlanTier.professional, PlanTier.agency]
    current_idx = tiers.index(PlanTier(sub.plan.tier))
    target_idx = tiers.index(req.tier)
    if target_idx >= current_idx:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use upgrade endpoint for upgrading",
        )

    await stripe_update_plan(
        sub.stripe_subscription_id, req.tier, proration_behavior="none"
    )
    return {"message": f"Downgrading to {req.tier.value} at period end"}


@router.post("/cancel")
async def cancel_subscription(
    user: UserInfo = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    user_id = parse_user_id(user)
    sub = await SubscriptionService.get_active_subscription(user_id, session=session)

    if not sub or not sub.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to cancel",
        )

    if sub.status in (SubscriptionStatus.canceled, SubscriptionStatus.suspended):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is already canceled or suspended",
        )

    await stripe_cancel_subscription(sub.stripe_subscription_id)
    return {
        "message": "Subscription will be canceled at the end of the billing period",
        "access_until": (
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
    }


@router.post("/reactivate")
async def reactivate_subscription(
    user: UserInfo = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    user_id = parse_user_id(user)
    sub = await SubscriptionService.get_active_subscription(user_id, session=session)

    if not sub or not sub.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No subscription found",
        )

    stripe_sub = await stripe_get_subscription(sub.stripe_subscription_id)
    if not stripe_sub.get("cancel_at_period_end"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is not scheduled for cancellation",
        )

    await stripe_reactivate_subscription(sub.stripe_subscription_id)
    return {"message": "Subscription reactivated"}


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    user: UserInfo = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    user_id = parse_user_id(user)
    stmt = (
        select(Invoice)
        .where(Invoice.user_id == user_id)
        .order_by(Invoice.created_at.desc())
        .limit(50)
    )
    result = await session.execute(stmt)
    invoices = result.scalars().all()

    return [
        InvoiceResponse(
            id=str(inv.id),
            invoice_number=inv.invoice_number,
            status=inv.status.value,
            total_gross=str(inv.total_gross),
            total_net=str(inv.total_net),
            vat_amount=str(inv.vat_amount),
            currency=inv.currency,
            period_start=inv.period_start.isoformat() if inv.period_start else None,
            period_end=inv.period_end.isoformat() if inv.period_end else None,
            paid_at=inv.paid_at.isoformat() if inv.paid_at else None,
            pdf_url=inv.pdf_url,
        )
        for inv in invoices
    ]


@router.post("/invoice-details")
async def update_invoice_details(
    req: InvoiceDetailRequest,
    user: UserInfo = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    user_id = parse_user_id(user)
    sub = await SubscriptionService.get_active_subscription(user_id, session=session)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription",
        )

    sub.extra_data = {
        **(sub.extra_data or {}),
        "company_name": req.company_name,
        "company_vat_id": req.company_vat_id,
        "company_address": req.company_address,
    }
    await session.commit()

    return {"message": "Invoice details updated"}
