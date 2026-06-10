import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import delete, select

from src.api.v1.router import router as v1_router
from src.compliance.data_governance import DataGovernance, DataType
from src.compliance.deletion_manager import DeletionManager
from src.config import settings
from src.db.database import async_session_factory, init_db
from src.db.models import ConsentRecord, DataRetentionLog, WebhookDelivery
from src.middleware.audit import AuditMiddleware


async def _expire_consent_records():
    async with async_session_factory() as session:
        gov = DataGovernance()
        cutoff = gov.get_policy(DataType.CONSENT).get_cutoff_date()
        result = await session.execute(
            select(ConsentRecord).where(ConsentRecord.expires_at.isnot(None), ConsentRecord.expires_at < cutoff, ConsentRecord.revoked_at.is_(None))
        )
        records = result.scalars().all()
        for record in records:
            record.revoked_at = cutoff
        if records:
            await session.commit()


async def _cleanup_expired_logs():
    async with async_session_factory() as session:
        gov = DataGovernance()
        cutoff = gov.get_policy(DataType.DELIVERY_LOG).get_cutoff_date()
        await session.execute(delete(WebhookDelivery).where(WebhookDelivery.created_at < cutoff))
        retention_cutoff = gov.get_policy(DataType.LOG).get_cutoff_date()
        await session.execute(delete(DataRetentionLog).where(DataRetentionLog.performed_at < retention_cutoff))
        await session.commit()


async def _process_pending_deletions():
    async with async_session_factory() as session:
        manager = DeletionManager(session)
        await manager.process_all_pending()


async def _compliance_cleanup_loop():
    while True:
        with suppress(Exception):
            await _process_pending_deletions()
        with suppress(Exception):
            await _expire_consent_records()
        with suppress(Exception):
            await _cleanup_expired_logs()
        await asyncio.sleep(settings.compliance_cleanup_interval_hours * 3600)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Path(settings.app_data_dir).mkdir(parents=True, exist_ok=True)
    await init_db()
    cleanup_task = asyncio.create_task(_compliance_cleanup_loop())
    yield
    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task


app = FastAPI(title=settings.app_name, version="0.1.0", docs_url=settings.docs_url, openapi_url=settings.openapi_url, lifespan=lifespan)
app.add_middleware(AuditMiddleware)
app.include_router(v1_router, prefix="/api")
