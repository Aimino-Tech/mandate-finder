from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, JSON, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import NullPool

from mandate_finder.config import settings

_async_engine: AsyncEngine | None = None


def get_async_engine() -> AsyncEngine:
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            poolclass=NullPool,
        )
    return _async_engine


AsyncSessionLocal = async_sessionmaker(
    get_async_engine(),
    class_=AsyncSession,
    expire_on_commit=False,
)

SyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=create_engine(
        settings.database_url_sync,
        echo=settings.debug,
        pool_pre_ping=True,
    ),
)


# JSONB-compatible type: uses JSONB on PostgreSQL, JSON on other dialects (e.g. SQLite).
JsonType = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, type]] = {
        dict[str, Any]: JsonType,
        list[Any]: JsonType,
    }
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_db_sync() -> Generator[Session, None, None]:
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()
