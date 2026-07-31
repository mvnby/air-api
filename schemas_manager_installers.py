"""Manager installer API contracts."""

from typing import List, Optional

from pydantic import BaseModel

from schemas_common import Meta


class ManagerInstallerBase(BaseModel):
    name: str
    is_active: bool = True
    default_rate: Optional[float] = None
    telegram_id: Optional[int] = None


class ManagerInstallerCreatePayload(ManagerInstallerBase):
    pass


class ManagerInstallerUpdatePayload(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    default_rate: Optional[float] = None
    telegram_id: Optional[int] = None


class ManagerInstallerResponse(ManagerInstallerBase):
    id: int


class ManagerInstallerListResponse(BaseModel):
    items: List[ManagerInstallerResponse]
    meta: Meta
