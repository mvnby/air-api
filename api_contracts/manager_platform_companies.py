"""Platform directory and company site visibility; no provisioning or DNS writes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CompanyDomainResponse(BaseModel):
    id: int
    hostname: str
    status: Literal["pending", "active", "disabled"]
    is_primary: bool
    verified_at: datetime | None


class CompanySiteResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    status: Literal["draft", "active", "disabled"]
    city: str | None
    default_locale: str
    currency: str
    is_default: bool
    domains: list[CompanyDomainResponse]


class CompanySitesResponse(BaseModel):
    items: list[CompanySiteResponse]
    total: int
    page: int
    limit: int


class CompanyOwnerResponse(BaseModel):
    staff_user_id: int
    display_name: str


class PlatformCompanyResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    kind: str
    status: Literal["active", "disabled"]
    is_system: bool
    demo_read_only: bool
    updated_at: datetime
    owners: list[CompanyOwnerResponse]
    active_staff_count: int
    sites: list[CompanySiteResponse]


class PlatformCompanyListResponse(BaseModel):
    items: list[PlatformCompanyResponse]
    total: int
    page: int
    limit: int


class PlatformCompanyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_updated_at: datetime
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    status: Literal["active", "disabled"] | None = None

    @model_validator(mode="after")
    def require_change(self):
        changes = self.model_fields_set - {"expected_updated_at"}
        if not changes or any(getattr(self, field) is None for field in changes):
            raise ValueError("Укажите название или состояние компании")
        return self
