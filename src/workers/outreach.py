from __future__ import annotations

import os

from taskiq import TaskiqState
from taskiq.events import TaskiqEvents
from taskiq_aio_pika import AioPikaBroker
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import settings
from src.services.outreach.campaign import CampaignService
from src.services.outreach.delivery import DeliveryService


def _get_amqp_url() -> str:
    return os.environ.get("TASKIQ_AMQP_URL", "amqp://guest:guest@localhost:5672/")


engine = create_async_engine(settings.database_url)
session_factory = async_sessionmaker(engine, expire_on_commit=False)
broker = AioPikaBroker(_get_amqp_url())


async def on_startup(state: TaskiqState) -> None:
    state.campaign_service = None
    state.delivery_service = None


async def on_shutdown(state: TaskiqState) -> None:
    await engine.dispose()


broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, on_startup)
broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, on_shutdown)


@broker.task
async def batch_generate_task(
    campaign_id: str,
    template_id: str | None = None,
    tone: str | None = None,
    motivation_reason: str = "",
    market_signals: list[str] | None = None,
) -> dict:
    async with session_factory() as session:
        service = CampaignService(session)
        messages = await service.generate_messages(
            campaign_id=campaign_id,
            template_id=template_id,
            tone=tone,
            motivation_reason=motivation_reason,
            market_signals=market_signals or [],
        )
        return {
            "campaign_id": campaign_id,
            "messages_count": len(messages),
            "status": "completed",
        }


@broker.task
async def send_campaign_task(campaign_id: str) -> dict:
    async with session_factory() as session:
        service = CampaignService(session)
        success = await service.send_messages(campaign_id)
        campaign = await service.get(campaign_id)
        return {
            "campaign_id": campaign_id,
            "success": success,
            "sent_count": campaign.sent_count if campaign else 0,
            "status": "sent" if success else "failed",
        }


@broker.task
async def track_delivery_task(
    delivery_id: str,
    status: str,
    external_message_id: str | None = None,
    error_message: str | None = None,
) -> dict:
    async with session_factory() as session:
        service = DeliveryService(session)
        delivery = await service.update_status(
            delivery_id=delivery_id,
            status=status,
            external_message_id=external_message_id,
            error_message=error_message,
        )
        return {
            "delivery_id": delivery_id,
            "status": delivery.status if delivery else "not_found",
        }
