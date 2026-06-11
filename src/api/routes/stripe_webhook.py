from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_session
from src.models.billing import (
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    PlanTier,
    Subscription,
    SubscriptionStatus,
)
from src.services.billing.stripe_client import (
    parse_subscription_status,
    tier_from_price_id,
)
from src.services.billing.subscription_service import SubscriptionService
from src.services.billing.vat import calculate_vat, validate_vat_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/stripe", tags=["stripe-webhooks"])


@router.post("")
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
        ) from None
    except stripe.error.SignatureVerificationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        ) from None

    handlers = {
        "checkout.session.completed": _handle_checkout_completed,
        "customer.subscription.updated": _handle_subscription_updated,
        "customer.subscription.deleted": _handle_subscription_deleted,
        "invoice.paid": _handle_invoice_paid,
        "invoice.payment_failed": _handle_invoice_payment_failed,
        "customer.subscription.trial_will_end": _handle_trial_will_end,
    }

    handler = handlers.get(event["type"])
    if handler:
        try:
            await handler(event, session)
        except Exception as e:
            logger.exception("Webhook handler failed for %s: %s", event["type"], e)

    return {"received": True}


async def _handle_checkout_completed(
    event: stripe.Event,
    session: AsyncSession,
):
    data = event["data"]["object"]
    metadata = data.get("metadata", {})
    user_id_str = metadata.get("user_id")
    plan_tier_str = metadata.get("plan_tier")

    if not user_id_str or not plan_tier_str:
        logger.warning("Missing metadata in checkout.session.completed")
        return

    user_id = uuid.UUID(user_id_str)
    stripe_sub_id = data.get("subscription")

    if data.get("mode") == "subscription" and stripe_sub_id:
        stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)

        status = parse_subscription_status(stripe_sub.status)
        period_start = (
            datetime.fromtimestamp(
                stripe_sub.current_period_start, tz=timezone.UTC
            )
            if stripe_sub.get("current_period_start")
            else None
        )
        period_end = (
            datetime.fromtimestamp(
                stripe_sub.current_period_end, tz=timezone.UTC
            )
            if stripe_sub.get("current_period_end")
            else None
        )
        trial_end = (
            datetime.fromtimestamp(stripe_sub.trial_end, tz=timezone.UTC)
            if stripe_sub.get("trial_end")
            else None
        )

        await SubscriptionService.create_or_update_subscription(
            user_id=user_id,
            plan_tier=PlanTier(plan_tier_str),
            stripe_subscription_id=stripe_sub_id,
            stripe_customer_id=data.get("customer"),
            status=status,
            period_start=period_start,
            period_end=period_end,
            trial_end=trial_end,
            session=session,
        )


async def _handle_subscription_updated(
    event: stripe.Event,
    session: AsyncSession,
):
    data = event["data"]["object"]
    stripe_subscription_id = data.get("id")
    stripe_customer_id = data.get("customer")
    status = parse_subscription_status(data.get("status"))

    items = data.get("items", {}).get("data", [])
    price_id = items[0]["price"]["id"] if items else None
    tier = tier_from_price_id(price_id) if price_id else None

    period_start = (
        datetime.fromtimestamp(data["current_period_start"], tz=timezone.UTC)
        if data.get("current_period_start")
        else None
    )
    period_end = (
        datetime.fromtimestamp(data["current_period_end"], tz=timezone.UTC)
        if data.get("current_period_end")
        else None
    )
    trial_end = (
        datetime.fromtimestamp(data["trial_end"], tz=timezone.UTC)
        if data.get("trial_end")
        else None
    )

    stmt = select(Subscription).where(
        Subscription.stripe_subscription_id == stripe_subscription_id
    )
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()

    if not sub:
        logger.warning(
            "No subscription found for stripe id: %s", stripe_subscription_id
        )
        metadata = data.get("metadata", {})
        user_id_str = metadata.get("user_id")
        plan_tier_str = metadata.get("plan_tier") or (tier.value if tier else None)

        if user_id_str and plan_tier_str:
            await SubscriptionService.create_or_update_subscription(
                user_id=uuid.UUID(user_id_str),
                plan_tier=PlanTier(plan_tier_str),
                stripe_subscription_id=stripe_subscription_id,
                stripe_customer_id=stripe_customer_id,
                status=status,
                period_start=period_start,
                period_end=period_end,
                trial_end=trial_end,
                session=session,
            )
        return

    if tier:
        plan = await SubscriptionService.get_plan_by_tier(tier, session=session)
        if plan:
            sub.plan_id = plan.id

    sub.stripe_customer_id = stripe_customer_id
    sub.status = status
    sub.current_period_start = period_start
    sub.current_period_end = period_end
    sub.trial_end = trial_end

    if data.get("cancel_at_period_end") and not sub.canceled_at:
        sub.canceled_at = datetime.now(timezone.UTC)
    elif not data.get("cancel_at_period_end"):
        sub.canceled_at = None

    if data.get("ended_at"):
        sub.ended_at = datetime.fromtimestamp(data["ended_at"], tz=timezone.UTC)

    await session.commit()


async def _handle_subscription_deleted(
    event: stripe.Event,
    session: AsyncSession,
):
    data = event["data"]["object"]
    stripe_subscription_id = data.get("id")

    stmt = select(Subscription).where(
        Subscription.stripe_subscription_id == stripe_subscription_id
    )
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()

    if sub:
        sub.status = SubscriptionStatus.canceled
        sub.ended_at = datetime.now(timezone.UTC)
        await session.commit()


async def _handle_invoice_paid(
    event: stripe.Event,
    session: AsyncSession,
):
    data = event["data"]["object"]
    stripe_invoice_id = data.get("id")
    stripe_subscription_id = data.get("subscription")
    total = data.get("total", 0)
    currency = data.get("currency", "eur").upper()

    stmt = select(Subscription).where(
        Subscription.stripe_subscription_id == stripe_subscription_id
    )
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()

    if not sub:
        logger.warning("No subscription for invoice %s", stripe_invoice_id)
        return

    period_start = data.get("period_start")
    period_end = data.get("period_end")

    invoice = Invoice(
        user_id=sub.user_id,
        subscription_id=sub.id,
        stripe_invoice_id=stripe_invoice_id,
        invoice_number=data.get("number", stripe_invoice_id),
        status=InvoiceStatus.paid,
        total_gross=Decimal(total) / 100,
        total_net=Decimal(total) / 100,
        vat_amount=Decimal(0),
        currency=currency,
        period_start=(
            datetime.fromtimestamp(period_start, tz=timezone.UTC)
            if period_start
            else None
        ),
        period_end=(
            datetime.fromtimestamp(period_end, tz=timezone.UTC)
            if period_end
            else None
        ),
        paid_at=datetime.now(timezone.UTC),
        pdf_url=data.get("invoice_pdf"),
        extra_data=data.get("metadata"),
    )

    company_name = None
    company_vat_id = None
    if sub.extra_data:
        company_name = sub.extra_data.get("company_name")
        company_vat_id = sub.extra_data.get("company_vat_id")

    invoice.company_name = company_name
    invoice.company_vat_id = company_vat_id

    if company_vat_id:
        try:
            vat_info = await validate_vat_id(company_vat_id)
            vat_result = calculate_vat(
                Decimal(total) / 100,
                is_b2b=True,
                vat_id_valid=vat_info.get("valid"),
            )
            invoice.vat_rate = vat_result.rate
            invoice.vat_amount = vat_result.amount
            invoice.total_net = Decimal(total) / 100 - vat_result.amount
        except Exception:
            logger.exception("VAT calculation failed")

    lines = data.get("lines", {}).get("data", [])
    for line in lines:
        line_item = InvoiceLineItem(
            invoice_id=invoice.id,
            description=line.get("description", ""),
            quantity=line.get("quantity", 1),
            unit_price_net=Decimal(line.get("unit_amount", 0)) / 100,
            total_net=Decimal(line.get("amount", 0)) / 100,
        )
        session.add(line_item)

    session.add(invoice)

    if sub.status != SubscriptionStatus.active:
        sub.status = SubscriptionStatus.active
    await session.commit()


async def _handle_invoice_payment_failed(
    event: stripe.Event,
    session: AsyncSession,
):
    data = event["data"]["object"]
    stripe_subscription_id = data.get("subscription")

    stmt = select(Subscription).where(
        Subscription.stripe_subscription_id == stripe_subscription_id
    )
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()

    if sub:
        sub.status = SubscriptionStatus.past_due
        await session.commit()


async def _handle_trial_will_end(
    event: stripe.Event,
    session: AsyncSession,
):
    data = event["data"]["object"]
    stripe_subscription_id = data.get("id")

    stmt = select(Subscription).where(
        Subscription.stripe_subscription_id == stripe_subscription_id
    )
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()

    if sub and sub.trial_end:
        remaining = (sub.trial_end - datetime.now(timezone.UTC)).days
        logger.info(
            "Trial will end for user %s in %d days",
            sub.user_id,
            remaining,
        )
