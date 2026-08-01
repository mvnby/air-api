"""Public catalog revision contracts."""

from datetime import datetime

from pydantic import BaseModel


class CatalogRevisionResponse(BaseModel):
    revision: int
    storefront_revision: int
    cache_key: str
    updated_at: datetime
