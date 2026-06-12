"""Consolidated FastAPI application for Mandate Finder.

This is the single source of truth for all API routes. All other
app instances in the project tree are deprecated and should redirect
here.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.mandate_finder.api.routes import ab_testing, auth, dedup, insights, users
from src.mandate_finder.api.routes.billing import router as billing_router
from src.mandate_finder.api.routes.stripe_webhook import router as stripe_webhook_router
from src.mandate_finder.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix=settings.api_prefix)


@api_router.get("/")
def api_root() -> dict[str, str]:
    return {"service": settings.app_name}


api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(ab_testing.router)
api_router.include_router(insights.router)
api_router.include_router(billing_router)
api_router.include_router(stripe_webhook_router)
api_router.include_router(dedup.router)

# Include V1 routes (CRM, enrichment, pipeline, outreach, webhooks)
try:
    from src.api.v1.router import router as v1_router

    api_router.include_router(v1_router)
    logger.info("V1 API routes included (CRM, enrichment, pipeline, outreach, webhooks)")
except ImportError:
    logger.warning("V1 API routes not available — run install with src/ package")

# Include search profile routes (legacy module at mandate_finder/api/routes.py)
try:
    from src.mandate_finder.api.routes.search_profiles import router as search_profiles_router

    api_router.include_router(search_profiles_router)
    logger.info("Search profile routes included")
except ImportError:
    logger.warning("Search profile routes not available")

# Include competitor insight routes (from src.api)
try:
    from src.api.routes.competitor import router as competitor_router

    api_router.include_router(competitor_router)
    logger.info("Competitor insight routes included")
except ImportError:
    logger.warning("Competitor insight routes not available")

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs"}
