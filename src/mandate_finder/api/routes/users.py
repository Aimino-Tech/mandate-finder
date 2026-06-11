from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from mandate_finder.api.deps import (
    CurrentUser,
    DbSession,
    ensure_app_user,
    require_admin,
)
from mandate_finder.models.organization import Organization, OrganizationMember
from mandate_finder.models.user import User
from mandate_finder.schemas.user import (
    ChangeRoleRequest,
    InviteRequest,
    OrgResponse,
    SwitchOrgRequest,
    TeamMemberResponse,
    UserResponse,
)
from mandate_finder.services.audit import write_audit_log

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    db: DbSession, current_user: CurrentUser
) -> UserResponse:
    user = await ensure_app_user(db, current_user)
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        user_type=user.user_type,
    )


@router.get("/team", response_model=list[TeamMemberResponse])
async def list_team(
    db: DbSession, current_user: CurrentUser
) -> list[TeamMemberResponse]:
    user = await ensure_app_user(db, current_user)
    if not user.organization_id:
        return []

    result = await db.execute(
        select(
            User.id,
            User.username,
            User.email,
            OrganizationMember.role,
        ).join(
            OrganizationMember,
            OrganizationMember.user_id == User.id,
        ).where(
            OrganizationMember.organization_id == user.organization_id
        )
    )
    rows = result.all()
    return [
        TeamMemberResponse(id=row.id, username=row.username, email=row.email, role=row.role)
        for row in rows
    ]


@router.get("/organizations", response_model=list[OrgResponse])
async def list_organizations(
    db: DbSession, current_user: CurrentUser
) -> list[OrgResponse]:
    user = await ensure_app_user(db, current_user)
    result = await db.execute(
        select(
            Organization.id,
            Organization.name,
            OrganizationMember.role,
        ).join(
            OrganizationMember,
            OrganizationMember.organization_id == Organization.id,
        ).where(
            OrganizationMember.user_id == user.id
        )
    )
    rows = result.all()
    orgs = [
        OrgResponse(id=row.id, name=row.name, role=row.role, active=row.id == user.organization_id)
        for row in rows
    ]
    return orgs


@router.post("/switch-org")
async def switch_organization(
    data: SwitchOrgRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, str]:
    user = await ensure_app_user(db, current_user)
    member = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.organization_id == data.organization_id,
        )
    )
    if member.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization.",
        )
    user.organization_id = data.organization_id
    await db.commit()
    await write_audit_log(
        db,
        user_id=user.id,
        organization_id=data.organization_id,
        action="org.switch",
        resource_type="organization",
        resource_id=str(data.organization_id),
    )
    return {"status": "ok", "active_org_id": str(data.organization_id)}


@router.post("/invite", status_code=status.HTTP_201_CREATED, response_model=TeamMemberResponse)
async def invite_member(
    data: InviteRequest,
    db: DbSession,
    current_user: CurrentUser,
    _: Any = require_admin,
) -> TeamMemberResponse:
    inviter = await ensure_app_user(db, current_user)
    if not inviter.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must belong to an organization to invite members.",
        )

    existing = await db.execute(select(User).where(User.email == data.email))
    existing_user = existing.scalar_one_or_none()
    if existing_user:
        existing_member = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == existing_user.id,
                OrganizationMember.organization_id == inviter.organization_id,
            )
        )
        if existing_member.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this organization.",
            )

        org_member = OrganizationMember(
            organization_id=inviter.organization_id,
            user_id=existing_user.id,
            role=data.role,
        )
        db.add(org_member)
        existing_user.organization_id = inviter.organization_id
        await db.commit()
        await db.refresh(org_member)
        await write_audit_log(
            db,
            user_id=inviter.id,
            organization_id=inviter.organization_id,
            action="member.invite",
            resource_type="user",
            resource_id=str(existing_user.id),
            details={"email": data.email, "role": data.role},
        )
        return TeamMemberResponse(
            id=existing_user.id,
            username=existing_user.username,
            email=existing_user.email,
            role=org_member.role,
        )

    new_user = User(
        username=data.email.split("@")[0],
        email=data.email,
        organization_id=inviter.organization_id,
    )
    db.add(new_user)
    await db.flush()

    org_member = OrganizationMember(
        organization_id=inviter.organization_id,
        user_id=new_user.id,
        role=data.role,
    )
    db.add(org_member)
    await db.commit()
    await db.refresh(new_user)
    await db.refresh(org_member)
    await write_audit_log(
        db,
        user_id=inviter.id,
        organization_id=inviter.organization_id,
        action="member.invite",
        resource_type="user",
        resource_id=str(new_user.id),
        details={"email": data.email, "role": data.role},
    )
    return TeamMemberResponse(
        id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        role=org_member.role,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(
    user_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
    _: Any = require_admin,
) -> None:
    user = await ensure_app_user(db, current_user)
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    if target.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not in your organization.",
        )

    members = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == target.id
        )
    )
    for member in members.scalars().all():
        await db.delete(member)

    await db.delete(target)
    await db.commit()
    await write_audit_log(
        db,
        user_id=user.id,
        organization_id=user.organization_id,
        action="member.remove",
        resource_type="user",
        resource_id=str(user_id),
    )


@router.put("/{user_id}/role", response_model=TeamMemberResponse)
async def change_user_role(
    user_id: UUID,
    data: ChangeRoleRequest,
    db: DbSession,
    current_user: CurrentUser,
    _: Any = require_admin,
) -> TeamMemberResponse:
    user = await ensure_app_user(db, current_user)
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == user.organization_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of your organization.",
        )
    member.role = data.role
    await db.commit()
    await db.refresh(member)
    await write_audit_log(
        db,
        user_id=user.id,
        organization_id=user.organization_id,
        action="member.role.change",
        resource_type="user",
        resource_id=str(user_id),
        details={"new_role": data.role},
    )

    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return TeamMemberResponse(
        id=target.id,
        username=target.username,
        email=target.email,
        role=member.role,
    )
