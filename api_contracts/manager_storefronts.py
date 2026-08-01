from pydantic import BaseModel, Field


class ManagerStorefrontResponse(BaseModel):
    slug: str
    display_name: str
    city: str | None = None
    default_locale: str
    currency: str
    is_default: bool
    is_current: bool


class ManagerStorefrontListResponse(BaseModel):
    items: list[ManagerStorefrontResponse] = Field(default_factory=list)
