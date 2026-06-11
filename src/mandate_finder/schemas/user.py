from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    user_type: str

    model_config = {"from_attributes": True}


class TeamMemberResponse(BaseModel):
    id: UUID
    username: str
    email: str
    role: str

    model_config = {"from_attributes": True}


class InviteRequest(BaseModel):
    email: str
    role: str = "member"


class ChangeRoleRequest(BaseModel):
    role: str


class OrgResponse(BaseModel):
    id: UUID
    name: str
    role: str
    active: bool


class SwitchOrgRequest(BaseModel):
    organization_id: UUID
