from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DocumentDriveStatusResponse(BaseModel):
    connected: bool
    provider: Literal["google_drive"] = "google_drive"
    account_label: str | None = None
    managed_folder_url: str | None = None
    connected_at: datetime | None = None
    last_verified_at: datetime | None = None
    last_error_code: str | None = None


class DocumentDriveAuthorizationUrlResponse(BaseModel):
    url: str
