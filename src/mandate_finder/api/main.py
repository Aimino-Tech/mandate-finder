from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mandate_finder.api.routes import auth, users
from mandate_finder.config import settings

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

app.include_router(api_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs"}
