from pydantic import BaseModel


class PublicStorefrontContextResponse(BaseModel):
    tenant_slug: str
    tenant_kind: str
    storefront_slug: str
    display_name: str
    hostname: str
    city: str | None = None
    default_locale: str
    currency: str
