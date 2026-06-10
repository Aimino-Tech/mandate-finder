from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from src.api.v1.admin_deps import require_admin
from src.db.database import get_session
from src.db.models import AlertConfig, APIKey, MetricEvent
from src.services.admin_metrics import (
    get_current_health_snapshot,
    get_dashboard_metrics,
    get_pipeline_by_source,
    get_pipeline_metrics,
    get_pipeline_totals,
    get_system_health,
    record_metric,
)

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


class RecordMetricRequest(BaseModel):
    metric_type: str
    value: float
    source: str | None = None
    labels: dict[str, Any] | None = None


class AlertConfigCreate(BaseModel):
    metric_type: str
    condition: str
    threshold: float
    window_minutes: int = 15
    slack_webhook_url: str | None = None


class AlertConfigUpdate(BaseModel):
    condition: str | None = None
    threshold: float | None = None
    window_minutes: int | None = None
    slack_webhook_url: str | None = None
    enabled: bool | None = None


@router.get("/dashboard")
async def admin_dashboard(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await get_dashboard_metrics(session, days)


@router.get("/pipeline")
async def admin_pipeline(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await get_pipeline_metrics(session, days)


@router.get("/pipeline/sources")
async def admin_pipeline_sources(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> dict:
    sources = await get_pipeline_by_source(session, days)
    totals = await get_pipeline_totals(session, days)
    return {"sources": sources, "totals": totals}


@router.get("/health")
async def admin_health(
    days: int = Query(7, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await get_system_health(session, days)


@router.get("/health/current")
async def admin_health_now(
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await get_current_health_snapshot(session)


@router.post("/metrics", status_code=201)
async def admin_record_metric(
    body: RecordMetricRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await record_metric(
        session,
        metric_type=body.metric_type,
        value=body.value,
        source=body.source,
        labels=body.labels,
    )
    return {"status": "ok"}


@router.get("/api-keys")
async def admin_list_api_keys(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(APIKey).order_by(APIKey.created_at.desc()).offset(skip).limit(limit)
    )
    keys = result.scalars().all()
    return {
        "api_keys": [
            {
                "id": k.id,
                "name": k.name,
                "tier": k.tier,
                "scopes": k.scopes,
                "is_active": k.is_active,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            }
            for k in keys
        ],
        "total": await session.scalar(select(func.count(APIKey.id))),
    }


class UpdateApiKeyTierRequest(BaseModel):
    tier: str


@router.patch("/api-keys/{key_id}/tier")
async def admin_update_api_key_tier(
    key_id: str,
    body: UpdateApiKeyTierRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if body.tier not in ("solo", "professional", "agency"):
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Invalid tier")
    result = await session.execute(select(APIKey).where(APIKey.id == key_id))
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="API key not found")
    key.tier = body.tier
    await session.commit()
    await session.refresh(key)
    return {"status": "ok", "id": key.id, "tier": key.tier}


@router.get("/export")
async def admin_export_metrics(
    metric_type: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    source: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    since = datetime.now(UTC) - timedelta(days=days)
    date_col = func.date(MetricEvent.recorded_at)
    query = select(
        date_col.label("date"),
        MetricEvent.value,
        MetricEvent.source,
        MetricEvent.metric_type,
    ).where(
        MetricEvent.metric_type == metric_type,
        MetricEvent.recorded_at >= since,
    )
    if source:
        query = query.where(MetricEvent.source == source)
    query = query.order_by(MetricEvent.recorded_at)

    result = await session.execute(query)
    rows = result.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "metric_type", "value", "source"])
    for row in rows:
        writer.writerow([str(row.date), row.metric_type, row.value, row.source or ""])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=metrics.csv"},
    )


@router.get("/alerts")
async def admin_list_alerts(
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    result = await session.execute(
        select(AlertConfig).order_by(AlertConfig.metric_type)
    )
    return [
        {
            "id": a.id,
            "metric_type": a.metric_type,
            "condition": a.condition,
            "threshold": a.threshold,
            "window_minutes": a.window_minutes,
            "slack_webhook_url": a.slack_webhook_url,
            "enabled": a.enabled,
            "last_triggered_at": a.last_triggered_at.isoformat() if a.last_triggered_at else None,
        }
        for a in result.scalars().all()
    ]


@router.post("/alerts", status_code=201)
async def admin_create_alert(
    body: AlertConfigCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if body.condition not in ("gt", "lt", "gte", "lte"):
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Condition must be one of: gt, lt, gte, lte")
    alert = AlertConfig(
        metric_type=body.metric_type,
        condition=body.condition,
        threshold=body.threshold,
        window_minutes=body.window_minutes,
        slack_webhook_url=body.slack_webhook_url,
    )
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return {
        "id": alert.id,
        "metric_type": alert.metric_type,
        "condition": alert.condition,
        "threshold": alert.threshold,
        "window_minutes": alert.window_minutes,
        "slack_webhook_url": alert.slack_webhook_url,
        "enabled": alert.enabled,
        "last_triggered_at": alert.last_triggered_at.isoformat() if alert.last_triggered_at else None,
    }


@router.put("/alerts/{alert_id}")
async def admin_update_alert(
    alert_id: str,
    body: AlertConfigUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(select(AlertConfig).where(AlertConfig.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Alert config not found")
    if body.condition is not None:
        alert.condition = body.condition
    if body.threshold is not None:
        alert.threshold = body.threshold
    if body.window_minutes is not None:
        alert.window_minutes = body.window_minutes
    if body.slack_webhook_url is not None:
        alert.slack_webhook_url = body.slack_webhook_url
    if body.enabled is not None:
        alert.enabled = body.enabled
    await session.commit()
    await session.refresh(alert)
    return {
        "id": alert.id,
        "metric_type": alert.metric_type,
        "condition": alert.condition,
        "threshold": alert.threshold,
        "window_minutes": alert.window_minutes,
        "slack_webhook_url": alert.slack_webhook_url,
        "enabled": alert.enabled,
        "last_triggered_at": alert.last_triggered_at.isoformat() if alert.last_triggered_at else None,
    }


@router.delete("/alerts/{alert_id}", status_code=204)
async def admin_delete_alert(
    alert_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(select(AlertConfig).where(AlertConfig.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="Alert config not found")
    await session.delete(alert)
    await session.commit()
