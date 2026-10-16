from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

InvitationRole = Literal["owner", "admin", "manager", "catalog_editor"]


class ManagerStaffInvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: InvitationRole


class ManagerStaffInvitationCreated(BaseModel):
    id: int
    role: InvitationRole
    expires_at: datetime
    invite_url: str


class ManagerStaffInvitationItem(BaseModel):
    id: int
    role: InvitationRole
    created_at: datetime
    expires_at: datetime
    status: Literal["pending", "accepted", "revoked", "expired"]


class ManagerStaffInvitationList(BaseModel):
    items: list[ManagerStaffInvitationItem]
    total: int
    page: int
    limit: int


class StaffInvitationToken(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=100)


class StaffInvitationPreview(BaseModel):
    company_name: str
    role: InvitationRole
    expires_at: datetime


class StaffInvitationAcceptExisting(StaffInvitationToken):
    mode: Literal["existing"]


class StaffInvitationAcceptNew(StaffInvitationToken):
    mode: Literal["new"]
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=9, max_length=72)
    display_name: str = Field(min_length=1, max_length=160)


class StaffInvitationAcceptCredentials(StaffInvitationToken):
    mode: Literal["existing_credentials"]
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=72)


StaffInvitationAccept = Annotated[
    StaffInvitationAcceptExisting | StaffInvitationAcceptNew | StaffInvitationAcceptCredentials,
    Field(discriminator="mode"),
]


class StaffInvitationAccepted(BaseModel):
    tenant_id: int
    default_storefront_slug: str
