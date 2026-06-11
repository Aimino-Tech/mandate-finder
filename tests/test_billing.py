"""Tests for billing & subscription management."""
from __future__ import annotations

from datetime import UTC
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.invoice import Invoice
from mandate_finder.models.plan import PlanTier
from mandate_finder.models.subscription import Subscription
from mandate_finder.models.user import User
from mandate_finder.services.billing_service import (
    StripeClient,
    calculate_vat,
    ensure_default_plans,
    get_active_plans,
    requires_feature,
    tier_is_downgrade,
    tier_is_upgrade,
    user_has_feature,
)

# ── Unit tests (no DB) ────────────────────────────────────────────────────


class TestBillingService:
    def test_calculate_vat_b2c(self):
        vat, total = calculate_vat(4900, is_b2b=False)
        assert vat == 931  # 4900 * 19% = 931
        assert total == 5831

    def test_calculate_vat_b2b(self):
        vat, total = calculate_vat(4900, is_b2b=True)
        assert vat == 0
        assert total == 4900

    def test_tier_upgrade_true(self):
        assert tier_is_upgrade("solo", "professional") is True
        assert tier_is_upgrade("solo", "agency") is True
        assert tier_is_upgrade("professional", "agency") is True

    def test_tier_upgrade_false(self):
        assert tier_is_upgrade("professional", "solo") is False
        assert tier_is_upgrade("agency", "professional") is False
        assert tier_is_upgrade("solo", "solo") is False

    def test_tier_downgrade_true(self):
        assert tier_is_downgrade("agency", "professional") is True
        assert tier_is_downgrade("agency", "solo") is True
        assert tier_is_downgrade("professional", "solo") is True

    def test_tier_downgrade_false(self):
        assert tier_is_downgrade("solo", "professional") is False
        assert tier_is_downgrade("solo", "agency") is False
        assert tier_is_downgrade("solo", "solo") is False

    def test_requires_feature(self):
        assert requires_feature("crm_integrations") == "professional"
        assert requires_feature("max_searches") == "solo"
        assert requires_feature("priority_support") == "agency"

    def test_user_has_feature(self):
        assert user_has_feature("agency", "crm_integrations") is True
        assert user_has_feature("professional", "crm_integrations") is True
        assert user_has_feature("solo", "crm_integrations") is False
        assert user_has_feature("solo", "max_searches") is True

    def test_stripe_client_dev_mode(self):
        client = StripeClient()
        assert client._dev_mode is True  # No API key in test


class TestPlanModel:
    def test_plan_tier_values(self):
        assert PlanTier.SOLO.value == "solo"
        assert PlanTier.PROFESSIONAL.value == "professional"
        assert PlanTier.AGENCY.value == "agency"


# ── Integration tests (DB + API) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_plans(async_client: AsyncClient, db_session: AsyncSession):
    """GET /billing/plans returns seeded plans."""
    await ensure_default_plans(db_session)

    response = await async_client.get("/api/v1/billing/plans")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 3
    tiers = {p["tier"] for p in data}
    assert tiers == {"solo", "professional", "agency"}


@pytest.mark.asyncio
async def test_list_plans_create_defaults(async_client: AsyncClient):
    """GET /billing/plans auto-seeds plans when empty."""
    response = await async_client.get("/api/v1/billing/plans")
    assert response.status_code == 200
    data = response.json()
    tiers = {p["tier"] for p in data}
    assert "solo" in tiers
    assert "professional" in tiers
    assert "agency" in tiers


@pytest.mark.asyncio
async def test_subscribe_with_free_trial(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
):
    """POST /billing/subscribe creates a subscription with trial."""
    await ensure_default_plans(db_session)

    plans = await get_active_plans(db_session)
    solo_plan = [p for p in plans if p.tier == "solo"][0]

    response = await async_client.post(
        "/api/v1/billing/subscribe",
        headers=auth_headers,
        json={"plan_id": str(solo_plan.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("active", "trialing")
    assert data["subscription_id"] is not None


@pytest.mark.asyncio
async def test_subscribe_duplicate(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
):
    """POST /billing/subscribe returns 409 if already subscribed."""
    await ensure_default_plans(db_session)
    plans = await get_active_plans(db_session)
    solo_plan = [p for p in plans if p.tier == "solo"][0]

    await async_client.post(
        "/api/v1/billing/subscribe",
        headers=auth_headers,
        json={"plan_id": str(solo_plan.id)},
    )

    response = await async_client.post(
        "/api/v1/billing/subscribe",
        headers=auth_headers,
        json={"plan_id": str(solo_plan.id)},
    )
    assert response.status_code == 409
    assert "already has an active subscription" in response.text


@pytest.mark.asyncio
async def test_get_subscription(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
):
    """GET /billing/subscription returns current subscription."""
    await ensure_default_plans(db_session)
    plans = await get_active_plans(db_session)
    solo_plan = [p for p in plans if p.tier == "solo"][0]

    await async_client.post(
        "/api/v1/billing/subscribe",
        headers=auth_headers,
        json={"plan_id": str(solo_plan.id)},
    )

    response = await async_client.get(
        "/api/v1/billing/subscription", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["plan_id"] == str(solo_plan.id)
    assert data["status"] in ("active", "trialing")


@pytest.mark.asyncio
async def test_get_subscription_no_sub(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
):
    """GET /billing/subscription returns null when not subscribed."""
    response = await async_client.get(
        "/api/v1/billing/subscription", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
async def test_upgrade(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
):
    """POST /billing/upgrade changes to higher-tier plan."""
    await ensure_default_plans(db_session)
    plans = await get_active_plans(db_session)
    solo_plan = [p for p in plans if p.tier == "solo"][0]
    pro_plan = [p for p in plans if p.tier == "professional"][0]

    await async_client.post(
        "/api/v1/billing/subscribe",
        headers=auth_headers,
        json={"plan_id": str(solo_plan.id)},
    )

    response = await async_client.post(
        "/api/v1/billing/upgrade",
        headers=auth_headers,
        json={"plan_id": str(pro_plan.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["plan_id"] == str(pro_plan.id)
    assert data["plan_name"] == "Professional"


@pytest.mark.asyncio
async def test_upgrade_not_upgrade(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
):
    """POST /billing/upgrade with downgrade returns 400."""
    await ensure_default_plans(db_session)
    plans = await get_active_plans(db_session)
    pro_plan = [p for p in plans if p.tier == "professional"][0]
    solo_plan = [p for p in plans if p.tier == "solo"][0]

    await async_client.post(
        "/api/v1/billing/subscribe",
        headers=auth_headers,
        json={"plan_id": str(pro_plan.id)},
    )

    response = await async_client.post(
        "/api/v1/billing/upgrade",
        headers=auth_headers,
        json={"plan_id": str(solo_plan.id)},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_downgrade(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
):
    """POST /billing/downgrade changes to lower-tier plan."""
    await ensure_default_plans(db_session)
    plans = await get_active_plans(db_session)
    pro_plan = [p for p in plans if p.tier == "professional"][0]
    solo_plan = [p for p in plans if p.tier == "solo"][0]

    await async_client.post(
        "/api/v1/billing/subscribe",
        headers=auth_headers,
        json={"plan_id": str(pro_plan.id)},
    )

    response = await async_client.post(
        "/api/v1/billing/downgrade",
        headers=auth_headers,
        json={"plan_id": str(solo_plan.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["plan_id"] == str(solo_plan.id)
    assert data["plan_name"] == "Solo"


@pytest.mark.asyncio
async def test_cancel_subscription(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
):
    """POST /billing/cancel cancels the subscription."""
    await ensure_default_plans(db_session)
    plans = await get_active_plans(db_session)
    solo_plan = [p for p in plans if p.tier == "solo"][0]

    await async_client.post(
        "/api/v1/billing/subscribe",
        headers=auth_headers,
        json={"plan_id": str(solo_plan.id)},
    )

    response = await async_client.post("/api/v1/billing/cancel", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "canceled"
    assert data["canceled_at"] is not None


@pytest.mark.asyncio
async def test_cancel_no_subscription(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
):
    """POST /billing/cancel returns 404 if no active subscription."""
    response = await async_client.post("/api/v1/billing/cancel", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_invoices(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
):
    """GET /billing/invoices returns invoices for user."""
    await ensure_default_plans(db_session)
    plans = await get_active_plans(db_session)
    solo_plan = [p for p in plans if p.tier == "solo"][0]

    await async_client.post(
        "/api/v1/billing/subscribe",
        headers=auth_headers,
        json={"plan_id": str(solo_plan.id)},
    )

    # Seed an invoice directly
    result = await db_session.execute(
        Subscription.__table__.select().where(Subscription.user_id.isnot(None))
    )
    sub = result.fetchone()
    if sub:
        invoice = Invoice(
            subscription_id=sub.id,
            stripe_invoice_id="in_test_123",
            amount_eur=4900,
            vat_percentage=19,
            vat_amount=931,
            total_eur=5831,
            status="paid",
        )
        db_session.add(invoice)
        await db_session.commit()

    response = await async_client.get(
        "/api/v1/billing/invoices", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_billing_portal(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
):
    """POST /billing/portal returns a URL."""
    response = await async_client.post(
        "/api/v1/billing/portal", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "url" in data


@pytest.mark.asyncio
async def test_list_plans_unauthorized(async_client: AsyncClient):
    """GET /billing/plans works without auth."""
    response = await async_client.get("/api/v1/billing/plans")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_subscribe_unauthorized(async_client: AsyncClient):
    """POST /billing/subscribe requires auth."""
    response = await async_client.post(
        "/api/v1/billing/subscribe",
        json={"plan_id": str(uuid4())},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upgrade_no_subscription(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
):
    """POST /billing/upgrade returns 404 if no subscription."""
    response = await async_client.post(
        "/api/v1/billing/upgrade",
        headers=auth_headers,
        json={"plan_id": str(uuid4())},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dunning_worker(db_session: AsyncSession):
    """Test dunning worker processes past_due subscriptions."""
    from mandate_finder.workers.dunning import process_dunning

    await ensure_default_plans(db_session)
    plans = await get_active_plans(db_session)
    solo_plan = plans[0]

    # Create past_due subscription
    sub = Subscription(
        user_id=uuid4(),
        plan_id=solo_plan.id,
        status="past_due",
    )
    db_session.add(sub)
    await db_session.commit()

    actions = await process_dunning(db_session)
    assert len(actions) >= 1
    assert actions[0]["action"] == "retry_1"


@pytest.mark.asyncio
async def test_trial_expiry_worker(db_session: AsyncSession):
    """Test trial expiry worker detects ending trials."""
    from datetime import datetime, timedelta

    from mandate_finder.workers.trial_expiry import check_trial_expiry

    await ensure_default_plans(db_session)
    plans = await get_active_plans(db_session)
    solo_plan = plans[0]

    # Create trial ending in 2 days
    sub = Subscription(
        user_id=uuid4(),
        plan_id=solo_plan.id,
        status="trialing",
        trial_end_at=datetime.now(UTC) + timedelta(days=2),
    )
    db_session.add(sub)
    await db_session.commit()

    actions = await check_trial_expiry(db_session)
    assert len(actions) >= 1
    assert actions[0]["days_remaining"] in (1, 3, 7)


@pytest.mark.asyncio
async def test_trial_expiry_expired(db_session: AsyncSession):
    """Test trial expiry worker handles already-expired trials."""
    from datetime import datetime, timedelta

    from mandate_finder.workers.trial_expiry import check_trial_expiry

    await ensure_default_plans(db_session)
    plans = await get_active_plans(db_session)
    solo_plan = plans[0]

    sub = Subscription(
        user_id=uuid4(),
        plan_id=solo_plan.id,
        status="trialing",
        trial_end_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(sub)
    await db_session.commit()

    actions = await check_trial_expiry(db_session)
    assert any(a["action"] == "trial_expired" for a in actions)
