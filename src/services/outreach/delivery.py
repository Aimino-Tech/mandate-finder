from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import MessageDelivery, MessageVariant, OutreachMessage

DELIVERY_STATUSES = {"pending", "sent", "delivered", "bounced", "opened", "replied", "failed"}


class DeliveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_delivery(
        self,
        message_id: str,
        recipient_email: str,
        channel: str = "email",
    ) -> MessageDelivery | None:
        message = await self.session.execute(
            select(OutreachMessage).where(OutreachMessage.id == message_id)
        )
        msg = message.scalar_one_or_none()
        if msg is None:
            return None
        delivery = MessageDelivery(
            message_id=message_id,
            recipient_email=recipient_email,
            channel=channel,
        )
        self.session.add(delivery)
        await self.session.commit()
        await self.session.refresh(delivery)
        return delivery

    async def get_delivery(self, delivery_id: str) -> MessageDelivery | None:
        result = await self.session.execute(
            select(MessageDelivery).where(MessageDelivery.id == delivery_id)
        )
        return result.scalar_one_or_none()

    async def list_deliveries(
        self,
        message_id: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[MessageDelivery]:
        query = select(MessageDelivery)
        if message_id:
            query = query.where(MessageDelivery.message_id == message_id)
        if status:
            query = query.where(MessageDelivery.status == status)
        query = query.order_by(MessageDelivery.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(query)
        result_list: list[MessageDelivery] = list(result.scalars().all())
        return result_list

    async def update_status(
        self,
        delivery_id: str,
        status: str,
        external_message_id: str | None = None,
        error_message: str | None = None,
    ) -> MessageDelivery | None:
        if status not in DELIVERY_STATUSES:
            return None
        now = datetime.now(UTC)
        updates: dict[str, Any] = {"status": status, "attempt_count": MessageDelivery.attempt_count + 1}
        if external_message_id:
            updates["external_message_id"] = external_message_id
        if error_message:
            updates["error_message"] = error_message
        if status == "sent":
            updates["sent_at"] = now
        elif status == "delivered":
            updates["delivered_at"] = now
        elif status == "opened":
            updates["opened_at"] = now
        elif status == "replied":
            updates["replied_at"] = now
        await self.session.execute(
            update(MessageDelivery).where(MessageDelivery.id == delivery_id).values(**updates)
        )
        await self.session.commit()
        return await self.get_delivery(delivery_id)

    async def get_delivery_stats(self, message_id: str) -> dict[str, int]:
        deliveries = await self.list_deliveries(message_id=message_id)
        stats: dict[str, int] = {"total": len(deliveries)}
        for d in deliveries:
            s = d.status
            stats[s] = stats.get(s, 0) + 1
        return stats


class VariantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_variant(
        self,
        message_id: str,
        variant_label: str,
        subject: str,
        body_text: str,
        body_html: str = "",
    ) -> MessageVariant | None:
        message = await self.session.execute(
            select(OutreachMessage).where(OutreachMessage.id == message_id)
        )
        if message.scalar_one_or_none() is None:
            return None
        variant = MessageVariant(
            message_id=message_id,
            variant_label=variant_label,
            subject=subject,
            body_text=body_text,
            body_html=body_html or body_text.replace("\n", "<br>\n"),
        )
        self.session.add(variant)
        await self.session.commit()
        await self.session.refresh(variant)
        return variant

    async def get_variant(self, variant_id: str) -> MessageVariant | None:
        result = await self.session.execute(
            select(MessageVariant).where(MessageVariant.id == variant_id)
        )
        return result.scalar_one_or_none()

    async def list_variants(self, message_id: str) -> list[MessageVariant]:
        result = await self.session.execute(
            select(MessageVariant)
            .where(MessageVariant.message_id == message_id)
            .order_by(MessageVariant.created_at)
        )
        return list(result.scalars().all())

    async def score_variant(self, variant_id: str, score: float) -> MessageVariant | None:
        variant = await self.get_variant(variant_id)
        if variant is None:
            return None
        variant.score = score
        await self.session.commit()
        await self.session.refresh(variant)
        return variant

    async def declare_winner(self, variant_id: str) -> MessageVariant | None:
        variant = await self.get_variant(variant_id)
        if variant is None:
            return None
        existing = await self.list_variants(variant.message_id)
        for v in existing:
            v.is_winner = v.id == variant_id
        await self.session.commit()
        await self.session.refresh(variant)
        return variant
