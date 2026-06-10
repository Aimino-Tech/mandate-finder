from __future__ import annotations

from typing import Any

from sqlalchemy import select

from src.db.database import async_session_factory
from src.db.models import Webhook

COMPLIANCE_EVENTS = {
    "deletion.completed",
    "deletion.failed",
    "consent.revoked",
    "optout.registered",
}


async def dispatch_compliance_event(event: str, payload: dict[str, Any]) -> None:
    if event not in COMPLIANCE_EVENTS:
        return
    async with async_session_factory() as session:
        result = await session.execute(select(Webhook).where(Webhook.is_active.is_(True)))
        all_webhooks = result.scalars().all()
    matching = [w for w in all_webhooks if w.events and event in w.events]
    for webhook in matching:
        try:
            from src.services.webhook_service import dispatch_webhook
            await dispatch_webhook(webhook_id=webhook.id, event=event, payload=payload)
        except Exception:
            pass
