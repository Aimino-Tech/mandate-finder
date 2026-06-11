from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from src.db.database import get_session
from src.db.models import (
    APIKey,
    MessageDelivery,
    MessageVariant,
    OutreachCampaign,
    OutreachMessage,
    OutreachTemplate,
    RecipientProfile,
)
from src.middleware.rate_limit import authenticated_api_key
from src.services.outreach.campaign import CampaignService
from src.services.outreach.delivery import DeliveryService, VariantService
from src.services.outreach.schemas import (
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    DeliveryResponse,
    DeliveryStatsResponse,
    GenerateRequest,
    MessageResponse,
    OutreachTemplateCreate,
    OutreachTemplateResponse,
    OutreachTemplateUpdate,
    PreviewRequest,
    PreviewResponse,
    RecipientCreate,
    RecipientResponse,
    VariantCreate,
    VariantResponse,
)
from src.services.outreach.templates import OutreachTemplateService

router = APIRouter(prefix="/outreach", tags=["Outreach"])


def _template_to_response(t: OutreachTemplate) -> dict:
    return OutreachTemplateResponse(
        id=t.id,
        name=t.name,
        description=t.description,
        channel=t.channel,
        subject_template=t.subject_template,
        body_template=t.body_template,
        variables_schema=t.variables_schema,
        tone=t.tone,
        is_active=t.is_active,
        created_at=t.created_at,
        updated_at=t.updated_at,
    ).model_dump()


def _campaign_to_response(c: OutreachCampaign) -> dict:
    return CampaignResponse(
        id=c.id,
        name=c.name,
        target_company_name=c.target_company_name,
        target_company_domain=c.target_company_domain,
        target_industry=c.target_industry,
        tone=c.tone,
        status=c.status,
        total_messages=c.total_messages,
        sent_count=c.sent_count,
        opened_count=c.opened_count,
        replied_count=c.replied_count,
        bounced_count=c.bounced_count,
        scheduled_at=c.scheduled_at,
        sent_at=c.sent_at,
        completed_at=c.completed_at,
        created_at=c.created_at,
        updated_at=c.updated_at,
    ).model_dump()


def _recipient_to_response(r: RecipientProfile) -> dict:
    return RecipientResponse(
        id=r.id,
        campaign_id=r.campaign_id,
        first_name=r.first_name,
        last_name=r.last_name,
        title=r.title,
        email=r.email,
        phone=r.phone,
        linkedin_url=r.linkedin_url,
        company_name=r.company_name,
        company_domain=r.company_domain,
        confidence_score=r.confidence_score,
        created_at=r.created_at,
    ).model_dump()


def _message_to_response(m: OutreachMessage) -> dict:
    return MessageResponse(
        id=m.id,
        campaign_id=m.campaign_id,
        template_id=m.template_id,
        recipient_profile_id=m.recipient_profile_id,
        subject=m.subject,
        body_text=m.body_text,
        channel=m.channel,
        tone=m.tone,
        status=m.status,
        generated_by_model=m.generated_by_model,
        token_count=m.token_count,
        compliance_check_passed=m.compliance_check_passed,
        created_at=m.created_at,
        updated_at=m.updated_at,
    ).model_dump()


@router.post("/templates", response_model=OutreachTemplateResponse, status_code=201)
async def create_template(
    body: OutreachTemplateCreate,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    if not body.name.strip():
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Name is required")
    if not body.subject_template.strip():
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Subject template is required")
    if not body.body_template.strip():
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Body template is required")
    service = OutreachTemplateService(session)
    template = await service.create(
        name=body.name,
        description=body.description,
        channel=body.channel,
        subject_template=body.subject_template,
        body_template=body.body_template,
        tone=body.tone,
        variables_schema=body.variables_schema,
    )
    return _template_to_response(template)


@router.get("/templates", response_model=list[OutreachTemplateResponse])
async def list_templates(
    channel: str | None = Query(None),
    only_active: bool = Query(True),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = OutreachTemplateService(session)
    templates = await service.list(channel=channel, only_active=only_active, offset=offset, limit=limit)
    return [_template_to_response(t) for t in templates]


@router.get("/templates/{template_id}", response_model=OutreachTemplateResponse)
async def get_template(
    template_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = OutreachTemplateService(session)
    template = await service.get(template_id)
    if template is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Template not found")
    return _template_to_response(template)


@router.put("/templates/{template_id}", response_model=OutreachTemplateResponse)
async def update_template(
    template_id: str,
    body: OutreachTemplateUpdate,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = OutreachTemplateService(session)
    update_kwargs = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    template = await service.update(template_id, **update_kwargs)
    if template is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Template not found")
    return _template_to_response(template)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = OutreachTemplateService(session)
    deleted = await service.delete(template_id)
    if not deleted:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Template not found")


@router.post("/templates/{template_id}/preview", response_model=PreviewResponse)
async def preview_template(
    template_id: str,
    body: PreviewRequest,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = OutreachTemplateService(session)
    result = await service.preview(template_id, body.variables)
    if result is None:
        template = await service.get(template_id)
        if template is None:
            raise HTTPException(HTTP_404_NOT_FOUND, detail="Template not found")
        found_vars = set(body.variables.keys())
        expected = set(template.variables_schema or [])
        missing = expected - found_vars
        raise HTTPException(
            HTTP_400_BAD_REQUEST,
            detail=f"Missing required variables: {sorted(missing)}",
        )
    return PreviewResponse(**result)


@router.post("/campaigns", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    session: AsyncSession = Depends(get_session),
    api_key: APIKey = Depends(authenticated_api_key),
):
    if not body.name.strip():
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Name is required")
    if not body.target_company_name.strip():
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Target company name is required")
    service = CampaignService(session)
    campaign = await service.create(
        api_key_id=api_key.id,
        name=body.name,
        target_company_name=body.target_company_name,
        target_company_domain=body.target_company_domain,
        target_industry=body.target_industry,
        tone=body.tone,
    )
    return _campaign_to_response(campaign)


@router.get("/campaigns", response_model=list[CampaignResponse])
async def list_campaigns(
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    campaigns = await service.list_campaigns(api_key=api_key, status=status, offset=offset, limit=limit)
    return [_campaign_to_response(c) for c in campaigns]


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    campaign = await service.get(campaign_id)
    if campaign is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Campaign not found")
    return _campaign_to_response(campaign)


@router.put("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: str,
    body: CampaignUpdate,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    update_kwargs = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    campaign = await service.update(campaign_id, **update_kwargs)
    if campaign is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Campaign not found")
    return _campaign_to_response(campaign)


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    deleted = await service.delete(campaign_id)
    if not deleted:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Campaign not found")


@router.post("/campaigns/{campaign_id}/recipients", response_model=RecipientResponse, status_code=201)
async def add_recipient(
    campaign_id: str,
    body: RecipientCreate,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    if not body.email.strip() or "@" not in body.email:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Valid email is required")
    if not body.first_name.strip():
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="First name is required")
    service = CampaignService(session)
    recipient = await service.add_recipient(
        campaign_id=campaign_id,
        first_name=body.first_name,
        last_name=body.last_name,
        title=body.title,
        email=body.email,
        company_name=body.company_name or "",
        phone=body.phone,
        linkedin_url=body.linkedin_url,
        confidence_score=body.confidence_score,
        source_enrichment_id=body.source_enrichment_id,
    )
    if recipient is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Campaign not found")
    return _recipient_to_response(recipient)


@router.get("/campaigns/{campaign_id}/recipients", response_model=list[RecipientResponse])
async def list_recipients(
    campaign_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    recipients = await service.list_recipients(campaign_id, offset=offset, limit=limit)
    return [_recipient_to_response(r) for r in recipients]


@router.post("/campaigns/{campaign_id}/generate", response_model=list[MessageResponse])
async def generate_campaign_messages(
    campaign_id: str,
    body: GenerateRequest,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    messages = await service.generate_messages(
        campaign_id=campaign_id,
        template_id=body.template_id,
        tone=body.tone,
        motivation_reason=body.motivation_reason,
        market_signals=body.market_signals,
    )
    if not messages:
        campaign = await service.get(campaign_id)
        if campaign is None:
            raise HTTPException(HTTP_404_NOT_FOUND, detail="Campaign not found")
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="No recipients in campaign. Add recipients before generating messages.")
    return [_message_to_response(m) for m in messages]


@router.get("/campaigns/{campaign_id}/messages", response_model=list[MessageResponse])
async def list_campaign_messages(
    campaign_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    messages = await service.list_messages(campaign_id, offset=offset, limit=limit)
    return [_message_to_response(m) for m in messages]


@router.post("/campaigns/{campaign_id}/approve", response_model=CampaignResponse)
async def approve_campaign(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    success = await service.approve_messages(campaign_id)
    if not success:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Campaign not found")
    campaign = await service.get(campaign_id)
    assert campaign is not None
    return _campaign_to_response(campaign)


@router.post("/campaigns/{campaign_id}/send", response_model=CampaignResponse)
async def send_campaign(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    success = await service.send_messages(campaign_id)
    if not success:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Campaign not found")
    campaign = await service.get(campaign_id)
    assert campaign is not None
    return _campaign_to_response(campaign)


@router.post("/campaigns/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    success = await service.pause_campaign(campaign_id)
    if not success:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Campaign not found or not active")
    campaign = await service.get(campaign_id)
    assert campaign is not None
    return _campaign_to_response(campaign)


@router.post("/campaigns/{campaign_id}/resume", response_model=CampaignResponse)
async def resume_campaign(
    campaign_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = CampaignService(session)
    success = await service.resume_campaign(campaign_id)
    if not success:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Campaign not found or not paused")
    campaign = await service.get(campaign_id)
    assert campaign is not None
    return _campaign_to_response(campaign)


def _delivery_to_response(d: MessageDelivery) -> dict:
    return DeliveryResponse(
        id=d.id,
        message_id=d.message_id,
        recipient_email=d.recipient_email,
        channel=d.channel,
        status=d.status,
        external_message_id=d.external_message_id,
        attempt_count=d.attempt_count,
        error_message=d.error_message,
        sent_at=d.sent_at,
        delivered_at=d.delivered_at,
        opened_at=d.opened_at,
        replied_at=d.replied_at,
        created_at=d.created_at,
    ).model_dump()


def _variant_to_response(v: MessageVariant) -> dict:
    return VariantResponse(
        id=v.id,
        message_id=v.message_id,
        variant_label=v.variant_label,
        subject=v.subject,
        body_text=v.body_text,
        score=v.score,
        is_winner=v.is_winner,
        created_at=v.created_at,
    ).model_dump()


@router.get("/messages/{message_id}/deliveries", response_model=list[DeliveryResponse])
async def list_message_deliveries(
    message_id: str,
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = DeliveryService(session)
    deliveries = await service.list_deliveries(message_id=message_id, status=status, offset=offset, limit=limit)
    return [_delivery_to_response(d) for d in deliveries]


@router.get("/messages/{message_id}/deliveries/stats", response_model=DeliveryStatsResponse)
async def get_delivery_stats(
    message_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = DeliveryService(session)
    stats = await service.get_delivery_stats(message_id)
    return DeliveryStatsResponse(**stats)


@router.post("/messages/{message_id}/deliveries", response_model=DeliveryResponse, status_code=201)
async def create_delivery(
    message_id: str,
    recipient_email: str,
    channel: str = "email",
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    if not recipient_email or "@" not in recipient_email:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Valid email is required")
    service = DeliveryService(session)
    delivery = await service.create_delivery(message_id=message_id, recipient_email=recipient_email, channel=channel)
    if delivery is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Message not found")
    return _delivery_to_response(delivery)


@router.patch("/deliveries/{delivery_id}/status", response_model=DeliveryResponse)
async def update_delivery_status(
    delivery_id: str,
    status: str,
    external_message_id: str | None = Query(None),
    error_message: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = DeliveryService(session)
    delivery = await service.update_status(
        delivery_id=delivery_id,
        status=status,
        external_message_id=external_message_id,
        error_message=error_message,
    )
    if delivery is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Delivery not found")
    return _delivery_to_response(delivery)


@router.post("/messages/{message_id}/variants", response_model=VariantResponse, status_code=201)
async def create_variant(
    message_id: str,
    body: VariantCreate,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    if not body.variant_label.strip():
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Variant label is required")
    service = VariantService(session)
    variant = await service.create_variant(
        message_id=message_id,
        variant_label=body.variant_label,
        subject=body.subject,
        body_text=body.body_text,
    )
    if variant is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Message not found")
    return _variant_to_response(variant)


@router.get("/messages/{message_id}/variants", response_model=list[VariantResponse])
async def list_variants(
    message_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = VariantService(session)
    variants = await service.list_variants(message_id)
    return [_variant_to_response(v) for v in variants]


@router.post("/variants/{variant_id}/score", response_model=VariantResponse)
async def score_variant(
    variant_id: str,
    score: float,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = VariantService(session)
    variant = await service.score_variant(variant_id, score)
    if variant is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Variant not found")
    return _variant_to_response(variant)


@router.post("/variants/{variant_id}/declare-winner", response_model=VariantResponse)
async def declare_winner(
    variant_id: str,
    session: AsyncSession = Depends(get_session),
    _api_key: APIKey = Depends(authenticated_api_key),
):
    service = VariantService(session)
    variant = await service.declare_winner(variant_id)
    if variant is None:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Variant not found")
    return _variant_to_response(variant)
