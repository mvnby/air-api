from typing import Literal
from pydantic import BaseModel


class ManagerAccountCompany(BaseModel):
    tenant_id: int
    slug: str
    display_name: str
    role: str
    membership_id: int | None
    access_kind: Literal["membership", "platform_support"]
    is_system: bool
    demo_read_only: bool
    default_storefront_slug: str


class ManagerAccountCompaniesResponse(BaseModel):
    staff_user_id: int | None
    username: str
    is_platform_owner: bool
    default_tenant_id: int | None
    items: list[ManagerAccountCompany]
    total: int
    page: int
    limit: int
