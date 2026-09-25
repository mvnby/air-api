"""Manager confirmation and proposal attachment of installation snapshots."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from schemas_installation_price_book import InstallationPreviewResponse


class ManagerInstallationConfirmPayload(BaseModel):
    preview_ref: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    order_id: int = Field(ge=1)
    proposal_id: int = Field(ge=1)
    verified_service_only_keys: list[str] = Field(default_factory=list)


class ManagerInstallationConfirmResponse(BaseModel):
    estimate_id: int
    revision: int
    order_id: int
    proposal_id: int
    price_book_id: int
    price_book_revision: int
    total: Decimal
    customer_text: str
    created_at: datetime


class ManagerInstallationEstimateRevisionResponse(ManagerInstallationConfirmResponse):
    snapshot: dict


class ManagerInstallationAttachPayload(BaseModel):
    revision: int = Field(ge=1)
    mode: Literal["collapsed", "detailed"] = "collapsed"


class ManagerInstallationAttachedLine(BaseModel):
    link_id: int
    title: str
    price: Decimal


class ManagerInstallationAttachResponse(BaseModel):
    estimate_id: int
    revision: int
    order_id: int
    proposal_id: int
    mode: Literal["collapsed", "detailed"]
    total: Decimal
    lines: list[ManagerInstallationAttachedLine]


class ManagerInstallationPriceChanged(BaseModel):
    code: Literal["price_changed"] = "price_changed"
    current_revision: int | None = None
    fresh_preview: InstallationPreviewResponse
    new_consent_required: bool = True


class ManagerInstallationPreviewLine(BaseModel):
    title: str
    price: Decimal


class ManagerInstallationPreviewResponse(InstallationPreviewResponse):
    collapsed_lines: list[ManagerInstallationPreviewLine] = Field(default_factory=list)
    detailed_lines: list[ManagerInstallationPreviewLine] = Field(default_factory=list)
