from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from src.api.routes.competitor import router as competitor_router
from src.db.database import async_session_factory

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        _run_aggregation,
        "interval",
        hours=6,
        id="signal_aggregation",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


async def _run_aggregation():
    from src.workers.signal_aggregator import aggregate_company_signals

    async with async_session_factory() as session:
        await aggregate_company_signals(session)


app = FastAPI(
    title="Mandate Finder — Competitor Insights API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(competitor_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
