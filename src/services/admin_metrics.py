from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import MetricEvent


async def get_metric_trend(
    session: AsyncSession,
    metric_type: str,
    days: int = 30,
    source: str | None = None,
) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=days)
    date_col = func.date(MetricEvent.recorded_at)
    query = select(
        date_col.label("date"),
        func.avg(MetricEvent.value).label("value"),
    ).where(
        MetricEvent.metric_type == metric_type,
        MetricEvent.recorded_at >= since,
    )
    if source:
        query = query.where(MetricEvent.source == source)
    query = query.group_by(date_col).order_by("date")

    result = await session.execute(query)
    return [{"date": str(row.date), "value": float(row.value)} for row in result.all()]


async def get_dashboard_metrics(session: AsyncSession, days: int = 30) -> dict:
    mrr = await get_metric_trend(session, "mrr", days)
    active_users = await get_metric_trend(session, "active_users", days)
    churn = await get_metric_trend(session, "churn_rate", days)
    return {"mrr": mrr, "active_users": active_users, "churn_rate": churn}


async def get_pipeline_metrics(session: AsyncSession, days: int = 30) -> dict:
    ingested = await get_metric_trend(session, "jobs_ingested", days)
    enriched = await get_metric_trend(session, "jobs_enriched", days)
    scored = await get_metric_trend(session, "jobs_scored", days)
    agi_processed = await get_metric_trend(session, "agi_processed", days)
    agi_matched = await get_metric_trend(session, "agi_matched", days)
    agi_outreach = await get_metric_trend(session, "agi_outreach_generated", days)
    return {
        "ingested": ingested,
        "enriched": enriched,
        "scored": scored,
        "agi_processed": agi_processed,
        "agi_matched": agi_matched,
        "agi_outreach_generated": agi_outreach,
    }


async def get_pipeline_by_source(session: AsyncSession, days: int = 30) -> dict:
    sources_query = select(MetricEvent.source).distinct().where(
        MetricEvent.metric_type == "jobs_ingested"
    )
    sources_result = await session.execute(sources_query)
    sources = [row[0] for row in sources_result.all() if row[0]]

    result: dict = {}
    for source in sources:
        result[source] = await get_metric_trend(session, "jobs_ingested", days, source=source)
    return result


async def get_pipeline_totals(session: AsyncSession, days: int = 1) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    totals: dict = {}
    for metric_type in ("jobs_ingested", "jobs_enriched", "jobs_scored", "agi_processed", "agi_matched", "agi_outreach_generated"):
        query = select(func.sum(MetricEvent.value)).where(
            MetricEvent.metric_type == metric_type,
            MetricEvent.recorded_at >= since,
        )
        row = await session.execute(query)
        val = row.scalar()
        totals[metric_type] = float(val) if val is not None else 0.0
    return totals


async def get_system_health(session: AsyncSession, days: int = 7) -> dict:
    queue = await get_metric_trend(session, "worker_queue_depth", days)
    latency = await get_metric_trend(session, "api_latency_p95", days)
    error_rate = await get_metric_trend(session, "error_rate", days)
    return {
        "worker_queue_depth": queue,
        "api_latency_p95": latency,
        "error_rate": error_rate,
    }


async def get_current_health_snapshot(session: AsyncSession) -> dict:
    snapshot: dict = {}
    for metric_type in ("worker_queue_depth", "api_latency_p95", "error_rate"):
        since = datetime.now(UTC) - timedelta(hours=1)
        query = select(func.avg(MetricEvent.value)).where(
            MetricEvent.metric_type == metric_type,
            MetricEvent.recorded_at >= since,
        )
        row = await session.execute(query)
        val = row.scalar()
        snapshot[metric_type] = float(val) if val is not None else 0.0
    return snapshot


async def record_metric(
    session: AsyncSession,
    metric_type: str,
    value: float,
    source: str | None = None,
    labels: dict | None = None,
) -> MetricEvent:
    event = MetricEvent(
        metric_type=metric_type,
        value=value,
        source=source,
        labels=labels,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event
