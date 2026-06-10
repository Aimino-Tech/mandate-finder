import hashlib
import hmac
import json
import time as time_module
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.database import async_session_factory
from src.db.models import Webhook, WebhookDelivery


def _compute_signature(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def dispatch_webhook(webhook_id: str, event: str, payload: dict[str, Any]) -> WebhookDelivery:
    async with async_session_factory() as session:
        result = await session.execute(select(Webhook).where(Webhook.id == webhook_id, Webhook.is_active.is_(True)))
        webhook = result.scalar_one_or_none()
        if webhook is None:
            raise ValueError(f"Webhook {webhook_id} not found or inactive")
        delivery = WebhookDelivery(webhook_id=webhook_id, event=event, payload=payload, status="pending", attempt=0)
        session.add(delivery)
        await session.commit()
        await session.refresh(delivery)
    await _send_with_retry(delivery.id, webhook.url, webhook.secret, event, payload)
    return delivery


async def _send_with_retry(delivery_id: str, url: str, secret: str, event: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, default=str).encode()
    signature = _compute_signature(body, secret)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event,
        "X-Webhook-Signature": signature,
        "User-Agent": "MandateFinder-Webhook/1.0",
    }
    async with async_session_factory() as session:
        for attempt in range(1, settings.webhook_max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=settings.webhook_default_timeout) as client:
                    resp = await client.post(url, content=body, headers=headers)
                status = "delivered" if resp.is_success else "failed"
                await _update_delivery(session, delivery_id, status=status, attempt=attempt, response_code=resp.status_code, response_body=resp.text[:4096] if not resp.is_success else None)
                if resp.is_success:
                    return
            except httpx.TimeoutException as e:
                await _update_delivery(session, delivery_id, status="failed", attempt=attempt, error_message=f"Timeout: {e}")
            except httpx.RequestError as e:
                await _update_delivery(session, delivery_id, status="failed", attempt=attempt, error_message=str(e))
            if attempt < settings.webhook_max_retries:
                delay = min(settings.webhook_retry_base_delay * (2 ** (attempt - 1)), settings.webhook_retry_max_delay)
                next_retry = datetime.now(UTC).timestamp() + delay
                await _update_delivery(session, delivery_id, next_retry_at=datetime.fromtimestamp(next_retry, tz=UTC))
                time_module.sleep(delay)
        await _update_delivery(session, delivery_id, status="failed", error_message="Max retries exceeded")


async def _update_delivery(session: AsyncSession, delivery_id: str, **kwargs) -> None:
    result = await session.execute(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id))
    delivery = result.scalar_one_or_none()
    if delivery is None:
        return
    for key, value in kwargs.items():
        if key == "status" and value == "delivered":
            delivery.delivered_at = datetime.now(UTC)
        setattr(delivery, key, value) if key != "delivered_at" else None
    await session.commit()
