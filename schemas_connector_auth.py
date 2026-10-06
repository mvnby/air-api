"""Public OAuth responses; no persisted raw credentials."""

from datetime import datetime
from pydantic import BaseModel


class ConnectorTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str
    scope: str


class ConnectorGrantResponse(BaseModel):
    id: int
    client_id: str
    tenant_id: int
    storefront_id: int
    scopes: list[str]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


class ConnectorGrantListResponse(BaseModel):
    items: list[ConnectorGrantResponse]
    csrf_token: str
