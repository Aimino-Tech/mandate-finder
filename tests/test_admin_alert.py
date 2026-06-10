from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import AlertConfig, Base, MetricEvent
from src.workers.admin_alert import check_and_alert


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    async with session_local() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_check_and_alert_gt_triggered(db_session):
    alert = AlertConfig(
        metric_type="error_rate",
        condition="gt",
        threshold=0.1,
        window_minutes=15,
        slack_webhook_url=None,
        enabled=True,
    )
    db_session.add(alert)
    for val in [0.15, 0.2, 0.12]:
        db_session.add(MetricEvent(metric_type="error_rate", value=val))
    await db_session.commit()

    triggered = await check_and_alert(db_session)
    assert len(triggered) == 1
    assert triggered[0]["metric_type"] == "error_rate"
    assert triggered[0]["current_value"] > 0.1


@pytest.mark.asyncio
async def test_check_and_alert_gt_not_triggered(db_session):
    alert = AlertConfig(
        metric_type="error_rate",
        condition="gt",
        threshold=0.5,
        window_minutes=15,
        slack_webhook_url=None,
        enabled=True,
    )
    db_session.add(alert)
    for val in [0.1, 0.2, 0.3]:
        db_session.add(MetricEvent(metric_type="error_rate", value=val))
    await db_session.commit()

    triggered = await check_and_alert(db_session)
    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_check_and_alert_lt_triggered(db_session):
    alert = AlertConfig(
        metric_type="jobs_ingested",
        condition="lt",
        threshold=100.0,
        window_minutes=15,
        slack_webhook_url=None,
        enabled=True,
    )
    db_session.add(alert)
    db_session.add(MetricEvent(metric_type="jobs_ingested", value=50.0))
    await db_session.commit()

    triggered = await check_and_alert(db_session)
    assert len(triggered) == 1
    assert triggered[0]["metric_type"] == "jobs_ingested"


@pytest.mark.asyncio
async def test_check_and_alert_disabled_skipped(db_session):
    alert = AlertConfig(
        metric_type="error_rate",
        condition="gt",
        threshold=0.1,
        window_minutes=15,
        enabled=False,
    )
    db_session.add(alert)
    db_session.add(MetricEvent(metric_type="error_rate", value=0.5))
    await db_session.commit()

    triggered = await check_and_alert(db_session)
    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_check_and_alert_no_data_skipped(db_session):
    alert = AlertConfig(
        metric_type="error_rate",
        condition="gt",
        threshold=0.1,
        window_minutes=15,
        enabled=True,
    )
    db_session.add(alert)
    await db_session.commit()

    triggered = await check_and_alert(db_session)
    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_check_and_alert_updates_last_triggered(db_session):
    alert = AlertConfig(
        metric_type="error_rate",
        condition="gt",
        threshold=0.1,
        window_minutes=15,
        enabled=True,
    )
    db_session.add(alert)
    db_session.add(MetricEvent(metric_type="error_rate", value=0.5))
    await db_session.commit()
    assert alert.last_triggered_at is None

    await check_and_alert(db_session)
    assert alert.last_triggered_at is not None
    assert alert.last_triggered_at > datetime.now(UTC) - timedelta(seconds=10)
