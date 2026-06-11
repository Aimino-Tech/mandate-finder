from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mandate_finder.api.routes import router
from mandate_finder.db.base import Base
from mandate_finder.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Mandate Finder — Multi-Profile Search Engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
