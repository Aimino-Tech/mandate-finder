"""Stripe webhook handler — checkout, invoices, subscription changes."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from mandate_finder.api.deps import get_db
from mandate_finder.models.invoice import Invoice
from mandate_finder.models.subscription import Subscription
from mandate_finder.services.billing_service import StripeClient, calculate_vat, get_vat_percentage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing/webhook", tags=["billing"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default=""),
):
    """Handle incoming Stripe webhook events."""
    payload = await request.body()

    stripe = StripeClient()
    try:
        event = stripe.parse_webhook_event(payload, stripe_signature)
    except Exception as exc:
        logger.warning("Stripe webhook signature invalid: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        ) from exc

    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})

    logger.info("Stripe webhook received: %s", event_type)

    handlers = {
        "checkout.session.completed": _handle_checkout_completed,
        "invoice.paid": _handle_invoice_paid,
        "customer.subscription.updated": _handle_subscription_updated,
        "invoice.payment_failed": _handle_invoice_payment_failed,
    }

    handler = handlers.get(event_type)
    if handler:
        async for db in get_db():
            try:
                await handler(db, data_object)
            except Exception as exc:
                logger.exception("Webhook handler failed: %s", exc)
            break

    return {"status": "ok"}


async def _handle_checkout_completed(db, data: dict) -> None:
    """Handle checkout.session.completed — link subscription to user."""
    stripe_subscription_id = data.get("subscription")
    if not stripe_subscription_id:
        return

    # Find subscription by Stripe ID and update its status
    result = await db.execute(
        select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.status = "active"
        await db.commit()
        logger.info("Subscription %s activated via checkout", sub.id)


async def _handle_invoice_paid(db, data: dict) -> None:
    """Record a paid invoice."""
    stripe_invoice_id = data.get("id")
    stripe_subscription_id = data.get("subscription")
    amount_due = data.get("amount_due", 0)
    period_start = data.get("period_start")
    period_end = data.get("period_end")
    invoice_pdf = data.get("invoice_pdf")
    paid_at = data.get("status_transitions", {}).get("paid_at")

    if not stripe_subscription_id:
        return

    # Find the local subscription
    result = await db.execute(
        select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        logger.warning("No subscription found for Stripe sub %s", stripe_subscription_id)
        return

    vat_pct = get_vat_percentage(is_b2b=False)
    vat_amount, total = calculate_vat(amount_due, is_b2b=False)

    invoice = Invoice(
        subscription_id=sub.id,
        stripe_invoice_id=stripe_invoice_id,
        amount_eur=amount_due,
        vat_percentage=vat_pct,
        vat_amount=vat_amount,
        total_eur=total,
        status="paid",
        pdf_url=invoice_pdf,
        paid_at=datetime.fromtimestamp(paid_at, tz=UTC) if paid_at else None,
        period_start=datetime.fromtimestamp(period_start, tz=UTC) if period_start else None,
        period_end=datetime.fromtimestamp(period_end, tz=UTC) if period_end else None,
    )
    db.add(invoice)
    await db.commit()
    logger.info("Invoice %s recorded for subscription %s", stripe_invoice_id, sub.id)


async def _handle_subscription_updated(db, data: dict) -> None:
    """Sync subscription status changes from Stripe."""
    stripe_subscription_id = data.get("id")
    status = data.get("status")
    cancel_at = data.get("canceled_at")
    current_period_start = data.get("current_period_start")
    current_period_end = data.get("current_period_end")

    if not stripe_subscription_id:
        return

    result = await db.execute(
        select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        logger.warning("Unknown subscription %s in webhook", stripe_subscription_id)
        return

    if status:
        sub.status = status
    if cancel_at:
        sub.canceled_at = datetime.fromtimestamp(cancel_at, tz=UTC)
    if current_period_start:
        sub.current_period_start = datetime.fromtimestamp(
            current_period_start, tz=UTC
        )
    if current_period_end:
        sub.current_period_end = datetime.fromtimestamp(
            current_period_end, tz=UTC
        )

    await db.commit()
    logger.info("Subscription %s updated to status %s", sub.id, status)


async def _handle_invoice_payment_failed(db, data: dict) -> None:
    """Mark subscription as past_due on payment failure."""
    stripe_subscription_id = data.get("subscription")
    if not stripe_subscription_id:
        return

    result = await db.execute(
        select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.status = "past_due"
        await db.commit()
        logger.warning(
            "Payment failed for subscription %s — marked past_due", sub.id
        )
