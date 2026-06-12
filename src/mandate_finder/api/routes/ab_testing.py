"""A/B Testing API routes.

CRUD for variants and tests, statistical dashboard, promotion, and report export.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from mandate_finder.api.deps import get_current_user, get_db
from mandate_finder.schemas.ab_testing import (
    ABTestCreate,
    ABTestDashboard,
    ABTestResponse,
    ABTestStats,
    ABTestUpdate,
    ExportReportResponse,
    MessageVariantCreate,
    MessageVariantResponse,
    MessageVariantUpdate,
    PromoteVariantRequest,
    ReplyEventCreate,
    ReplyEventResponse,
)
from mandate_finder.services.ab_test_service import ABTestService

router = APIRouter(
    prefix="/ab-testing",
    tags=["A/B Testing"],
    dependencies=[Depends(get_current_user)],
)


async def get_service(db: AsyncSession = Depends(get_db)) -> ABTestService:
    return ABTestService(db)


# -- Message Variant CRUD ---------------------------------------------------

@router.post("/variants", response_model=MessageVariantResponse, status_code=201)
async def create_variant(
    body: MessageVariantCreate,
    service: ABTestService = Depends(get_service),
):
    variant = await service.create_variant(
        campaign_id=body.campaign_id,
        subject=body.subject,
        body=body.body,
        cta=body.cta,
        personalization_level=body.personalization_level,
        is_control=body.is_control,
    )
    return variant


@router.get("/variants/{variant_id}", response_model=MessageVariantResponse)
async def get_variant(
    variant_id: UUID,
    service: ABTestService = Depends(get_service),
):
    variant = await service.get_variant(variant_id)
    if not variant:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Variant not found")
    return variant


@router.get("/campaigns/{campaign_id}/variants", response_model=list[MessageVariantResponse])
async def list_variants(
    campaign_id: UUID,
    service: ABTestService = Depends(get_service),
):
    return list(await service.list_variants(campaign_id))


@router.patch("/variants/{variant_id}", response_model=MessageVariantResponse)
async def update_variant(
    variant_id: UUID,
    body: MessageVariantUpdate,
    service: ABTestService = Depends(get_service),
):
    variant = await service.update_variant(
        variant_id,
        **body.model_dump(exclude_none=True),
    )
    if not variant:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Variant not found")
    return variant


@router.delete("/variants/{variant_id}", status_code=204)
async def delete_variant(
    variant_id: UUID,
    service: ABTestService = Depends(get_service),
):
    deleted = await service.delete_variant(variant_id)
    if not deleted:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Variant not found")


# -- AB Test CRUD -----------------------------------------------------------

@router.post("/tests", response_model=ABTestResponse, status_code=201)
async def create_test(
    body: ABTestCreate,
    service: ABTestService = Depends(get_service),
):
    test = await service.create_test(
        campaign_id=body.campaign_id,
        name=body.name,
        control_variant_id=body.control_variant_id,
        significance_threshold=body.significance_threshold,
    )
    return test


@router.get("/tests/{test_id}", response_model=ABTestResponse)
async def get_test(
    test_id: UUID,
    service: ABTestService = Depends(get_service),
):
    test = await service.get_test(test_id)
    if not test:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Test not found")
    return test


@router.get("/campaigns/{campaign_id}/tests", response_model=list[ABTestResponse])
async def list_tests(
    campaign_id: UUID,
    service: ABTestService = Depends(get_service),
):
    return list(await service.list_tests(campaign_id))


@router.patch("/tests/{test_id}", response_model=ABTestResponse)
async def update_test(
    test_id: UUID,
    body: ABTestUpdate,
    service: ABTestService = Depends(get_service),
):
    test = await service.update_test(
        test_id,
        **body.model_dump(exclude_none=True),
    )
    if not test:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Test not found")
    return test


# -- Statistics & Dashboard -------------------------------------------------

@router.get("/tests/{test_id}/stats", response_model=dict)
async def get_test_stats(
    test_id: UUID,
    service: ABTestService = Depends(get_service),
):
    """Compute per-variant statistics and p-values vs control."""
    result = await service.compute_stats(test_id)
    if "error" in result:
        raise HTTPException(HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/tests/{test_id}/dashboard", response_model=ABTestDashboard)
async def get_dashboard(
    test_id: UUID,
    service: ABTestService = Depends(get_service),
):
    """Full performance dashboard with recommendation."""
    result = await service.get_dashboard(test_id)
    if "error" in result:
        raise HTTPException(HTTP_404_NOT_FOUND, detail=result["error"])
    return result  # type: ignore[return-value]


@router.post("/tests/{test_id}/promote", response_model=dict)
async def promote_variant(
    test_id: UUID,
    body: PromoteVariantRequest,
    service: ABTestService = Depends(get_service),
):
    """Manually promote a variant as the test winner."""
    result = await service.promote_variant(test_id, body.variant_id)
    if not result.get("promoted"):
        raise HTTPException(HTTP_400_BAD_REQUEST, detail=result.get("reason", "Promotion failed"))
    return result


@router.post("/tests/{test_id}/auto-promote", response_model=dict)
async def auto_promote(
    test_id: UUID,
    service: ABTestService = Depends(get_service),
):
    """Evaluate and auto-promote if statistical significance is reached."""
    result = await service.auto_promote(test_id)
    return result


@router.get("/tests/{test_id}/export", response_model=ExportReportResponse)
async def export_report(
    test_id: UUID,
    service: ABTestService = Depends(get_service),
):
    """Export a report with n, open rate, reply rate, p-value for each variant."""
    result = await service.export_report(test_id)
    if "error" in result:
        raise HTTPException(HTTP_404_NOT_FOUND, detail=result["error"])
    return result  # type: ignore[return-value]


# -- Reply Events -----------------------------------------------------------

@router.post("/reply-events", response_model=ReplyEventResponse, status_code=201)
async def create_reply_event(
    body: ReplyEventCreate,
    service: ABTestService = Depends(get_service),
):
    """Record a reply event (used by webhook handlers)."""
    event = await service.record_reply(
        campaign_id=body.campaign_id,
        message_id=body.message_id,
        channel=body.channel,
        handled_by_human=body.handled_by_human,
        raw_data=body.raw_data,
    )
    return event


@router.get("/campaigns/{campaign_id}/replies", response_model=list[ReplyEventResponse])
async def list_replies(
    campaign_id: UUID,
    limit: int = Query(100, ge=1, le=1000),
    service: ABTestService = Depends(get_service),
):
    return list(await service.list_replies(campaign_id, limit=limit))
