from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mandate_finder.models.organization import OrganizationMember, OrganizationRole
from mandate_finder.models.user import User


@pytest.mark.asyncio
async def test_list_team(
    async_client: AsyncClient, auth_headers: dict[str, str], test_user: User
) -> None:
    response = await async_client.get("/api/v1/users/team", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(u["id"] == str(test_user.id) for u in data)


@pytest.mark.asyncio
async def test_invite_member(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    response = await async_client.post(
        "/api/v1/users/invite",
        headers=auth_headers,
        json={"email": "newuser@test.com", "role": "member"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "member"
    assert data["email"] == "newuser@test.com"


@pytest.mark.asyncio
async def test_invite_duplicate(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
) -> None:
    response = await async_client.post(
        "/api/v1/users/invite",
        headers=auth_headers,
        json={"email": test_user.email, "role": "member"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_remove_user(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
) -> None:
    new_user = User(
        username="todelete",
        email="delete@test.com",
        propelauth_user_id="delete-user",
        organization_id=test_user.organization_id,
    )
    db_session.add(new_user)
    await db_session.commit()
    await db_session.refresh(new_user)

    member = OrganizationMember(
        organization_id=test_user.organization_id,
        user_id=new_user.id,
        role=OrganizationRole.MEMBER.value,
    )
    db_session.add(member)
    await db_session.commit()

    response = await async_client.delete(
        f"/api/v1/users/{new_user.id}",
        headers=auth_headers,
    )
    assert response.status_code == 204

    result = await db_session.execute(select(User).where(User.id == new_user.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_remove_user_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.delete(
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_change_role(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
) -> None:
    new_user = User(
        username="rolechange",
        email="rolechange@test.com",
        organization_id=test_user.organization_id,
    )
    db_session.add(new_user)
    await db_session.commit()
    await db_session.refresh(new_user)

    member = OrganizationMember(
        organization_id=test_user.organization_id,
        user_id=new_user.id,
        role=OrganizationRole.MEMBER.value,
    )
    db_session.add(member)
    await db_session.commit()

    response = await async_client.put(
        f"/api/v1/users/{new_user.id}/role",
        headers=auth_headers,
        json={"role": "viewer"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "viewer"


@pytest.mark.asyncio
async def test_viewer_cannot_invite(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
) -> None:
    result = await db_session.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == test_user.id,
            OrganizationMember.organization_id == test_user.organization_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        await db_session.delete(existing)
        await db_session.commit()

    member = OrganizationMember(
        organization_id=test_user.organization_id,
        user_id=test_user.id,
        role=OrganizationRole.VIEWER.value,
    )
    db_session.add(member)
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/users/invite",
        headers=auth_headers,
        json={"email": "shouldfail@test.com", "role": "member"},
    )
    assert response.status_code == 403
