"""Test configuration.

All tests use SQLite (in-memory) to avoid PostgreSQL dependency.
Includes a minimal Campaign model for FK resolution.
Monkey-patches JSONB -> JSON for SQLite compatibility.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, NullPool, String, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

# Force SQLite for all tests BEFORE any mandate_finder imports
os.environ.setdefault("MANDATE_DATABASE_URL", "sqlite+aiosqlite:///./.test_db.sqlite3")
os.environ.setdefault("MANDATE_DATABASE_URL_SYNC", "sqlite+pysqlite:///./.test_db.sqlite3")
os.environ.setdefault("MANDATE_DEBUG", "false")

# Ensure src/ is on the path so that mandate_finder resolves to the
# comprehensive package under src/mandate_finder/ (the consolidated app).
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

# Monkey-patch JSONB -> JSON for SQLite compatibility
# This must happen BEFORE any imports that do `from sqlalchemy.dialects.postgresql import JSONB`
import sqlalchemy.dialects.postgresql as _pg
_pg.JSONB = JSON

from mandate_finder.api.deps import get_db
from mandate_finder.api.main import app
from mandate_finder.config import settings
from mandate_finder.database import Base

# Override type_annotation_map for SQLite compatibility (JSONB -> JSON)
Base.type_annotation_map = {
    dict[str, Any]: JSON,
    list[Any]: JSON,
}

# Import all models so they are registered with Base.metadata
from mandate_finder.models import (  # noqa: F401, E402
    ABTest,
    AuditLog,
    MessageVariant,
    Organization,
    OrganizationMember,
    ReplyEvent,
    User,
)


# Create a minimal Campaign model for FK resolution in tests
class Campaign(Base):  # type: ignore[no-redef]
    __tablename__ = "outreach_campaigns"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), default="Test Campaign")


# Re-override settings after imports
settings.database_url = os.environ["MANDATE_DATABASE_URL"]
settings.database_url_sync = os.environ["MANDATE_DATABASE_URL_SYNC"]

TEST_DATABASE_URL: str = settings.database_url


@pytest.fixture(scope="session")
def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    return engine


@pytest_asyncio.fixture(autouse=True)
async def setup_db(test_engine) -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Teardown: only delete from tables that exist
    async with test_engine.begin() as conn:
        def delete_all(sync_conn):
            for table in reversed(Base.metadata.sorted_tables):
                try:
                    sync_conn.execute(table.delete())
                except Exception:
                    pass  # table might not exist or be empty
        await conn.run_sync(delete_all)


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_local = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_local() as session:
        yield session


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession) -> Organization:
    org = Organization(name="Test Agency")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_org: Organization) -> Any:
    from mandate_finder.models.user import User
    user = User(
        username="testuser",
        email="test@example.com",
        propelauth_user_id="local-dev-user",
        organization_id=test_org.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.dev_auth_token}"}


# A/B Testing fixtures
@pytest.fixture
def ab_db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.database import Base as ABBase

    engine = create_engine("sqlite:///:memory:")
    ABBase.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def ab_campaign(ab_db_session):
    from src.models.ab_test import Campaign

    c = Campaign(name="test-campaign", industry="tech", role_seniority="senior", company_size="enterprise")
    ab_db_session.add(c)
    ab_db_session.commit()
    return c


@pytest.fixture
def ab_control_variant(ab_db_session, ab_campaign):
    from src.models.ab_test import MessageVariant

    v = MessageVariant(
        campaign_id=ab_campaign.id,
        name="control",
        subject="Standard outreach",
        body="Hello, I wanted to reach out...",
        call_to_action="Schedule a call",
        personalization_level="low",
        channel="email",
        is_control=True,
    )
    ab_db_session.add(v)
    ab_db_session.commit()
    return v


@pytest.fixture
def ab_test_variants(ab_db_session, ab_campaign):
    from src.models.ab_test import MessageVariant

    variants = []
    configs = [
        ("personalized_high", "High personalization", "Hello {{name}}, I noticed your work at {{company}}...", "high"),
        ("personalized_medium", "Medium personalization", "Hi {{name}}, wanted to connect...", "medium"),
        ("direct_cta", "Direct call-to-action", "Book a demo today!", "low"),
    ]
    for name, subject, body, pl in configs:
        v = MessageVariant(
            campaign_id=ab_campaign.id,
            name=name,
            subject=subject,
            body=body,
            call_to_action="Reply for details",
            personalization_level=pl,
            channel="email",
        )
        ab_db_session.add(v)
        variants.append(v)
    ab_db_session.commit()
    return variants


@pytest.fixture
def ab_test(ab_db_session, ab_campaign, ab_control_variant, ab_test_variants):
    from src.models.ab_test import ABTest, ABTestVariant

    t = ABTest(
        campaign_id=ab_campaign.id,
        name="email-outreach-test",
        metric="reply_rate",
        significance_threshold=0.05,
        min_sample_size=30,
    )
    ab_db_session.add(t)
    ab_db_session.flush()
    for v in [ab_control_variant] + ab_test_variants:
        av = ABTestVariant(ab_test_id=t.id, variant_id=v.id)
        ab_db_session.add(av)
    ab_db_session.commit()
    return t


# Competitor Insights fixtures
import uuid
from datetime import UTC, datetime, timedelta

@pytest_asyncio.fixture
async def company_a(db_session: AsyncSession) -> "Company":
    from src.models.company import Company
    c = Company(id=uuid.uuid4(), name="Siemens AG", industry="Engineering", is_private=False)
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def company_b(db_session: AsyncSession) -> "Company":
    from src.models.company import Company
    c = Company(id=uuid.uuid4(), name="Bosch GmbH", industry="Engineering", is_private=False)
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def company_c(db_session: AsyncSession) -> "Company":
    from src.models.company import Company
    c = Company(id=uuid.uuid4(), name="SAP SE", industry="Technology", is_private=False)
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def private_company(db_session: AsyncSession) -> "Company":
    from src.models.company import Company
    c = Company(id=uuid.uuid4(), name="Private Corp", industry="Finance", is_private=True)
    db_session.add(c)
    await db_session.flush()
    return c
