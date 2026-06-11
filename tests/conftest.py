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
