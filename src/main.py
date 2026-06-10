from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.v1.router import router as v1_router
from src.config import settings
from src.db.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", docs_url=settings.docs_url, openapi_url=settings.openapi_url, lifespan=lifespan)
app.include_router(v1_router, prefix="/api")
