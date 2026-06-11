from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mandate_finder.api.deps import get_db
from mandate_finder.api.main import app
from mandate_finder.config import settings
from mandate_finder.database import Base
from mandate_finder.models.organization import Organization, OrganizationMember, OrganizationRole
from mandate_finder.models.user import User

TEST_DATABASE_URL = settings.database_url


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "db_required: mark test as needing a PostgreSQL database (skipped if no DB available)",
    )


def has_database() -> bool:
    """Check if the test PostgreSQL database is reachable."""
    try:
        import asyncpg, asyncio
        async def probe() -> bool:
            try:
                conn = await asyncpg.connect(
                    user="mandate", password="mandate",
                    database="mandate_finder", host="127.0.0.1",
                    port=5432, timeout=2,
                )
                await conn.close()
                return True
            except Exception:
                return False
        return asyncio.run(probe())
    except ImportError:
        return False


_HAS_DB = has_database()


@pytest.fixture(scope="session")
def test_engine():
    """Return async engine if DB available, else None (test skipped downstream)."""
    if not _HAS_DB:
        return None
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    return engine


@pytest_asyncio.fixture(autouse=True)
async def setup_db(test_engine) -> AsyncGenerator[None, None]:
    """Set up test database tables (no-op if no DB)."""
    if test_engine is None:
        yield
        return
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a DB session (skip if no DB)."""
    if test_engine is None:
        pytest.skip("PostgreSQL test database not available")
        return
    from sqlalchemy.ext.asyncio import async_sessionmaker
    session_local = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_local() as session:
        yield session


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTP test client (skip if no DB)."""
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
async def test_user(db_session: AsyncSession, test_org: Organization) -> User:
    user = User(
        username="testuser",
        email="test@example.com",
        propelauth_user_id="local-dev-user",
        organization_id=test_org.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    member = OrganizationMember(
        organization_id=test_org.id,
        user_id=user.id,
        role=OrganizationRole.ADMIN.value,
    )
    db_session.add(member)
    await db_session.commit()
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
