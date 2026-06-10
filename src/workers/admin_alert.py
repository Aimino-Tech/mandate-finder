from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AlertConfig, MetricEvent

logger = logging.getLogger(__name__)


async def check_and_alert(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(AlertConfig).where(AlertConfig.enabled.is_(True))
    )
    alerts = result.scalars().all()
    triggered: list[dict] = []

    for alert in alerts:
        since = datetime.now(UTC) - timedelta(minutes=alert.window_minutes)
        query = select(func.avg(MetricEvent.value)).where(
            MetricEvent.metric_type == alert.metric_type,
            MetricEvent.recorded_at >= since,
        )
        row = await session.execute(query)
        avg_value = row.scalar()

        if avg_value is None:
            continue

        should_trigger = (
            (alert.condition == "gt" and avg_value > alert.threshold)
            or (alert.condition == "lt" and avg_value < alert.threshold)
            or (alert.condition == "gte" and avg_value >= alert.threshold)
            or (alert.condition == "lte" and avg_value <= alert.threshold)
        )

        if should_trigger:
            payload = {
                "metric_type": alert.metric_type,
                "condition": alert.condition,
                "threshold": alert.threshold,
                "current_value": float(avg_value),
                "window_minutes": alert.window_minutes,
                "alert_id": alert.id,
            }
            triggered.append(payload)

            if alert.slack_webhook_url:
                await _post_to_slack(alert.slack_webhook_url, payload)

            alert.last_triggered_at = datetime.now(UTC)
            session.add(alert)

    await session.commit()
    return triggered


async def _post_to_slack(webhook_url: str, payload: dict) -> None:
    message = {
        "text": (
            f"🚨 *Alert Triggered*\n"
            f"• Metric: `{payload['metric_type']}`\n"
            f"• Condition: `{payload['condition']} {payload['threshold']}`\n"
            f"• Current value: `{payload['current_value']:.2f}`\n"
            f"• Window: {payload['window_minutes']} min"
        )
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=message, timeout=10)
            resp.raise_for_status()
            logger.info(
                "Slack alert sent for %s (value=%.2f)",
                payload["metric_type"],
                payload["current_value"],
            )
    except Exception as e:
        logger.error("Failed to post to Slack webhook: %s", e)
