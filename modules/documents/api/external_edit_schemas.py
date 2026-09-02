from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .schemas import NativeTemplateVersionItem


class ExternalEditSessionItem(BaseModel):
    id: str
    status: str
    edit_url: str | None = None
    can_edit: bool
    base_checksum_sha256: str
    remote_revision: str | None = None
    modified_at: datetime | None = None
    last_synced_at: datetime | None = None
    detail: str | None = None


class TemplateExternalEditSyncPayload(BaseModel):
    expected_base_checksum_sha256: str = Field(
        min_length=64, max_length=64, pattern="^[0-9a-fA-F]{64}$"
    )
    expected_remote_revision: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=160)


class TemplateExternalEditSyncResponse(BaseModel):
    session: ExternalEditSessionItem
    new_template_version: NativeTemplateVersionItem | None = None
