"""Tests for AIM-1500: Competitor Activity & Company Signals."""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.company_signal import CompanySignal
from mandate_finder.models.user import User
from mandate_finder.services.competitor_insights import (
    _apply_k_anonymity,
    add_to_watchlist,
    get_alternative_recommendations,
    get_company_competition,
    get_company_signal,
    get_heatmap,
    get_user_watchlist,
    log_activity_event,
    remove_from_watchlist,
)
from mandate_finder.workers.signal_aggregator import aggregate_signals

TEST_COMPANY_X_ID = uuid4()
TEST_COMPANY_Y_ID = uuid4()
TEST_COMPANY_Z_ID = uuid4()


# ---------------------------------------------------------------------------
# Unit: k-anonymity helper
# ---------------------------------------------------------------------------

class TestKAnonymity:
    def test_hides_below_threshold(self) -> None:
        assert _apply_k_anonymity(0) == 0
        assert _apply_k_anonymity(1) == 0
        assert _apply_k_anonymity(2) == 0

    def test_shows_at_or_above_threshold(self) -> None:
        assert _apply_k_anonymity(3) == 3
        assert _apply_k_anonymity(5) == 5
        assert _apply_k_anonymity(100) == 100


# ---------------------------------------------------------------------------
# Integration: activity events, aggregation, watchlist
# ---------------------------------------------------------------------------

class TestActivityEvents:
    """Verify activity event creation and k-anonymized aggregation."""

    @pytest.mark.asyncio
    async def test_log_activity_event(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        event = await log_activity_event(
            db_session,
            user_id=test_user.id,
            company_id=TEST_COMPANY_X_ID,
            activity_type="outreach",
        )
        assert event.id is not None
        assert event.user_id == test_user.id
        assert event.company_id == TEST_COMPANY_X_ID
        assert event.activity_type == "outreach"
        assert event.is_private is False

    @pytest.mark.asyncio
    async def test_company_competition_k_anonymity_hides_low(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """2 users target Company Y → hidden (<3, k-anonymity)."""
        another_user = User(
            username="another",
            email="another@test.com",
            organization_id=test_user.organization_id,
        )
        db_session.add(another_user)
        await db_session.commit()
        await db_session.refresh(another_user)

        # 2 users, each with 1 activity
        for user in [test_user, another_user]:
            await log_activity_event(
                db_session, user_id=user.id, company_id=TEST_COMPANY_Y_ID, activity_type="viewed",
            )

        count = await get_company_competition(db_session, TEST_COMPANY_Y_ID)
        assert count == 0, f"Expected 0 (k-anonymized), got {count}"

    @pytest.mark.asyncio
    async def test_company_competition_shows_high(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """5 users target Company X → shows '5 active agencies'."""
        users = [test_user]
        for i in range(4):
            u = User(
                username=f"user_{i}",
                email=f"user_{i}@test.com",
                organization_id=test_user.organization_id,
            )
            db_session.add(u)
            await db_session.commit()
            await db_session.refresh(u)
            users.append(u)

        for u in users:
            await log_activity_event(
                db_session, user_id=u.id, company_id=TEST_COMPANY_X_ID, activity_type="outreach",
            )

        count = await get_company_competition(db_session, TEST_COMPANY_X_ID)
        assert count >= 5, f"Expected >=5, got {count}"

    @pytest.mark.asyncio
    async def test_private_event_excluded_from_aggregation(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """User opts Company Z to private → excluded from aggregation."""
        # Add 3 users with non-private activity → should show
        users = [test_user]
        for i in range(2):
            u = User(
                username=f"private_test_user_{i}",
                email=f"private_test_{i}@test.com",
                organization_id=test_user.organization_id,
            )
            db_session.add(u)
            await db_session.commit()
            await db_session.refresh(u)
            users.append(u)

        for u in users:
            await log_activity_event(
                db_session, user_id=u.id, company_id=TEST_COMPANY_Z_ID, activity_type="applied",
            )

        # One user's activity is private
        await log_activity_event(
            db_session,
            user_id=test_user.id,
            company_id=TEST_COMPANY_Z_ID,
            activity_type="applied",
            is_private=True,
        )

        count_public = await get_company_competition(db_session, TEST_COMPANY_Z_ID, include_private=False)
        # Only 3 users have non-private events → should be >= 3
        assert count_public >= 3, f"Expected >=3 (public only), got {count_public}"


class TestSignalAggregation:
    """Verify the signal_aggregator worker."""

    @pytest.mark.asyncio
    async def test_aggregate_signals_creates_signals(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Aggregation creates CompanySignal records."""
        await log_activity_event(
            db_session, user_id=test_user.id, company_id=TEST_COMPANY_X_ID, activity_type="outreach",
        )
        # Need at least 3 users for k-anonymity
        for i in range(2):
            u = User(
                username=f"agg_user_{i}",
                email=f"agg_{i}@test.com",
                organization_id=test_user.organization_id,
            )
            db_session.add(u)
            await db_session.commit()
            await db_session.refresh(u)
            await log_activity_event(
                db_session, user_id=u.id, company_id=TEST_COMPANY_X_ID, activity_type="outreach",
            )

        signals = await aggregate_signals(db_session)
        assert len(signals) > 0
        signal = await get_company_signal(db_session, TEST_COMPANY_X_ID)
        assert signal is not None
        assert signal.competitor_count >= 3

    @pytest.mark.asyncio
    async def test_aggregate_with_no_events(
        self, db_session: AsyncSession
    ) -> None:
        """Aggregation with no events returns empty list."""
        signals = await aggregate_signals(db_session)
        assert signals == []


class TestWatchlist:
    """Verify watchlist CRUD operations."""

    @pytest.mark.asyncio
    async def test_add_to_watchlist(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        entry = await add_to_watchlist(
            db_session,
            user_id=test_user.id,
            company_id=TEST_COMPANY_X_ID,
            company_name="Test Corp",
        )
        assert entry.company_name == "Test Corp"
        assert entry.notify_on_change is True

    @pytest.mark.asyncio
    async def test_get_user_watchlist(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        await add_to_watchlist(
            db_session, user_id=test_user.id, company_id=TEST_COMPANY_X_ID, company_name="Test Corp",
        )
        entries = await get_user_watchlist(db_session, test_user.id)
        assert len(entries) >= 1

    @pytest.mark.asyncio
    async def test_remove_from_watchlist(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        entry = await add_to_watchlist(
            db_session, user_id=test_user.id, company_id=TEST_COMPANY_X_ID, company_name="Test Corp",
        )
        deleted = await remove_from_watchlist(db_session, test_user.id, entry.id)
        assert deleted is True

        # Verify it's gone
        entries = await get_user_watchlist(db_session, test_user.id)
        assert entry.id not in [e.id for e in entries]

    @pytest.mark.asyncio
    async def test_remove_nonexistent_watchlist(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        deleted = await remove_from_watchlist(db_session, test_user.id, uuid4())
        assert deleted is False


class TestAlternatives:
    """Verify alternative recommendations."""

    @pytest.mark.asyncio
    async def test_get_alternatives(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Query unwatched company → returns empty, not error."""
        # No signals exist → alternatives should be empty
        recs = await get_alternative_recommendations(db_session)
        assert isinstance(recs, list)

    @pytest.mark.asyncio
    async def test_alternatives_with_signals(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Alternatives include companies with lower competition."""
        signal = CompanySignal(
            company_id=uuid4(),
            company_name="Low Comp Co",
            competitor_count=1,
            trend="rising",
        )
        db_session.add(signal)
        await db_session.commit()

        recs = await get_alternative_recommendations(db_session)
        assert len(recs) >= 1
        assert recs[0]["company_name"] == "Low Comp Co"
        assert "lower" in recs[0]["rationale"].lower() or "opportunity" in recs[0]["rationale"].lower()


class TestHeatmap:
    """Verify heatmap endpoint behavior."""

    @pytest.mark.asyncio
    async def test_heatmap_empty(
        self, db_session: AsyncSession
    ) -> None:
        """No activity → empty heatmap."""
        items = await get_heatmap(db_session)
        assert items == []

    @pytest.mark.asyncio
    async def test_heatmap_with_activity(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Activity exists → heatmap returns companies."""
        await log_activity_event(
            db_session, user_id=test_user.id, company_id=TEST_COMPANY_X_ID, activity_type="outreach",
        )
        # Need >= 3 distinct users for k-anonymity
        for i in range(2):
            u = User(
                username=f"heat_user_{i}",
                email=f"heat_{i}@test.com",
                organization_id=test_user.organization_id,
            )
            db_session.add(u)
            await db_session.commit()
            await db_session.refresh(u)
            await log_activity_event(
                db_session, user_id=u.id, company_id=TEST_COMPANY_X_ID, activity_type="outreach",
            )

        items = await get_heatmap(db_session)
        assert len(items) >= 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestInsightsAPI:
    """Integration tests via HTTP API."""

    @pytest.mark.asyncio
    async def test_get_company_insights_not_found(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Query unwatched company → returns empty, not error."""
        random_id = uuid4()
        response = await async_client.get(
            f"/api/v1/insights/company/{random_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["company_id"] == str(random_id)
        assert data["competitor_count"] == 0

    @pytest.mark.asyncio
    async def test_get_company_insights_with_activity(
        self, async_client: AsyncClient, auth_headers: dict[str, str],
        db_session: AsyncSession, test_user: User,
    ) -> None:
        """5 users target Company X → shows '5 active agencies'."""
        users = [test_user]
        for i in range(4):
            u = User(
                username=f"api_user_{i}",
                email=f"api_{i}@test.com",
                organization_id=test_user.organization_id,
            )
            db_session.add(u)
            await db_session.commit()
            await db_session.refresh(u)
            users.append(u)

        for u in users:
            await log_activity_event(
                db_session, user_id=u.id, company_id=TEST_COMPANY_X_ID, activity_type="outreach",
            )

        # Run aggregation
        await aggregate_signals(db_session)

        response = await async_client.get(
            f"/api/v1/insights/company/{TEST_COMPANY_X_ID}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["competitor_count"] >= 5, f"Expected >=5, got {data['competitor_count']}"

    @pytest.mark.asyncio
    async def test_heatmap_endpoint(
        self, async_client: AsyncClient, auth_headers: dict[str, str],
        db_session: AsyncSession, test_user: User,
    ) -> None:
        response = await async_client.get(
            "/api/v1/insights/heatmap",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_alternatives_endpoint(
        self, async_client: AsyncClient, auth_headers: dict[str, str],
    ) -> None:
        response = await async_client.get(
            "/api/v1/insights/alternatives",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_watchlist_crud(
        self, async_client: AsyncClient, auth_headers: dict[str, str],
    ) -> None:
        # Create
        create_resp = await async_client.post(
            "/api/v1/insights/watchlist",
            headers=auth_headers,
            json={
                "company_id": str(TEST_COMPANY_X_ID),
                "company_name": "Test Corp",
                "notify_on_change": True,
            },
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["company_name"] == "Test Corp"
        watchlist_id = created["id"]

        # List
        list_resp = await async_client.get(
            "/api/v1/insights/watchlist",
            headers=auth_headers,
        )
        assert list_resp.status_code == 200
        entries = list_resp.json()
        assert any(e["id"] == watchlist_id for e in entries)

        # Delete
        delete_resp = await async_client.delete(
            f"/api/v1/insights/watchlist/{watchlist_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == 204

        # Verify deleted
        list_resp2 = await async_client.get(
            "/api/v1/insights/watchlist",
            headers=auth_headers,
        )
        entries2 = list_resp2.json()
        assert all(e["id"] != watchlist_id for e in entries2)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_watchlist(
        self, async_client: AsyncClient, auth_headers: dict[str, str],
    ) -> None:
        response = await async_client.delete(
            f"/api/v1/insights/watchlist/{uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_report_endpoint(
        self, async_client: AsyncClient, auth_headers: dict[str, str],
        db_session: AsyncSession, test_user: User,
    ) -> None:
        """Export report → includes signal timeline."""
        # Create some data
        await add_to_watchlist(
            db_session, user_id=test_user.id, company_id=TEST_COMPANY_X_ID, company_name="Test Corp",
        )

        response = await async_client.get(
            "/api/v1/insights/report",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "company_signals" in data
        assert "watchlist" in data
        assert "alternatives" in data
        assert "generated_at" in data
