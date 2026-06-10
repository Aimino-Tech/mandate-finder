from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

from src.core.pagination import CursorPage, paginate
from src.core.security import generate_webhook_secret
from src.db.database import get_session
from src.db.models import APIKey, Webhook, WebhookDelivery
from src.middleware.rate_limit import authenticated_api_key
from src.services.webhook_service import dispatch_webhook

VALID_EVENTS = {"lead.match", "campaign.completed", "decisionmaker.found", "trend.alert"}

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str]
    secret: str | None = None


class WebhookUpdate(BaseModel):
    url: HttpUrl | None = None
    events: list[str] | None = None
    is_active: bool | None = None


class WebhookTestRequest(BaseModel):
    event: str


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DeliveryResponse(BaseModel):
    id: str
    event: str
    status: str
    attempt: int
    response_code: int | None = None
    error_message: str | None = None
    created_at: datetime
    delivered_at: datetime | None = None


def _webhook_to_response(w: Webhook) -> dict:
    return WebhookResponse(id=w.id, url=w.url, events=w.events, is_active=w.is_active, created_at=w.created_at, updated_at=w.updated_at).model_dump()


def _delivery_to_response(d: WebhookDelivery) -> dict:
    return DeliveryResponse(id=d.id, event=d.event, status=d.status, attempt=d.attempt, response_code=d.response_code, error_message=d.error_message, created_at=d.created_at, delivered_at=d.delivered_at).model_dump()


@router.get("", response_model=CursorPage)
async def list_webhooks(api_key: APIKey = Depends(authenticated_api_key), cursor: str | None = None, limit: int = 50, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Webhook).where(Webhook.api_key_id == api_key.id).order_by(Webhook.created_at.desc()).limit(limit + 1))
    webhooks = result.scalars().all()
    return paginate([_webhook_to_response(w) for w in webhooks], cursor=cursor, limit=limit)


@router.post("", response_model=WebhookResponse, status_code=201)
async def create_webhook(body: WebhookCreate, api_key: APIKey = Depends(authenticated_api_key), session: AsyncSession = Depends(get_session)):
    invalid = [e for e in body.events if e not in VALID_EVENTS]
    if invalid:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail=f"Invalid events: {invalid}. Valid: {sorted(VALID_EVENTS)}")
    if not body.events:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="At least one event required")
    secret = body.secret or generate_webhook_secret()
    webhook = Webhook(api_key_id=api_key.id, url=str(body.url), secret=secret, events=body.events)
    session.add(webhook)
    await session.commit()
    await session.refresh(webhook)
    return _webhook_to_response(webhook)


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(webhook_id: str, api_key: APIKey = Depends(authenticated_api_key), session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Webhook).where(Webhook.id == webhook_id, Webhook.api_key_id == api_key.id))
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Webhook not found")
    return _webhook_to_response(webhook)


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(webhook_id: str, body: WebhookUpdate, api_key: APIKey = Depends(authenticated_api_key), session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Webhook).where(Webhook.id == webhook_id, Webhook.api_key_id == api_key.id))
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Webhook not found")
    if body.url is not None:
        webhook.url = str(body.url)
    if body.events is not None:
        invalid = [e for e in body.events if e not in VALID_EVENTS]
        if invalid:
            raise HTTPException(HTTP_400_BAD_REQUEST, detail=f"Invalid events: {invalid}")
        webhook.events = body.events
    if body.is_active is not None:
        webhook.is_active = body.is_active
    await session.commit()
    await session.refresh(webhook)
    return _webhook_to_response(webhook)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: str, api_key: APIKey = Depends(authenticated_api_key), session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Webhook).where(Webhook.id == webhook_id, Webhook.api_key_id == api_key.id))
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Webhook not found")
    webhook.is_active = False
    await session.commit()


@router.get("/{webhook_id}/deliveries", response_model=CursorPage)
async def list_deliveries(webhook_id: str, api_key: APIKey = Depends(authenticated_api_key), cursor: str | None = None, limit: int = 50, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(WebhookDelivery).join(Webhook).where(WebhookDelivery.webhook_id == webhook_id, Webhook.api_key_id == api_key.id).order_by(WebhookDelivery.created_at.desc()).limit(limit + 1))
    deliveries = result.scalars().all()
    return paginate([_delivery_to_response(d) for d in deliveries], cursor=cursor, limit=limit)


@router.post("/{webhook_id}/test", status_code=202)
async def test_webhook(webhook_id: str, body: WebhookTestRequest, _api_key: APIKey = Depends(authenticated_api_key)):
    if body.event not in VALID_EVENTS:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail=f"Invalid event: {body.event}. Valid: {sorted(VALID_EVENTS)}")
    try:
        await dispatch_webhook(webhook_id=webhook_id, event=body.event, payload={"test": True, "event": body.event, "message": "This is a test webhook from Mandate Finder"})
    except ValueError as e:
        raise HTTPException(HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception:
        raise HTTPException(HTTP_409_CONFLICT, detail="Webhook delivery failed") from None
    return {"status": "accepted", "event": body.event}
