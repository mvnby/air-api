"""Manager confirmation and proposal attachment of installation snapshots."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from schemas_installation_price_book import InstallationPreviewResponse, InstallationPreviewPayload


class ManagerInstallationPreviewPayload(InstallationPreviewPayload):
    # Explicit service-only tariff selection is accepted by Manager routes only.
    tariff_selections: dict[str, str] = Field(default_factory=dict)


class ManagerInstallationStandardTariff(BaseModel):
    code: str
    title: str
    description: str
    price: Decimal
    product_kind: str
    indoor_type: str | None = None
    route_m: Decimal
    holes_by_type: dict[str, Decimal]
    capacity_min_kw: Decimal | None = None
    capacity_max_kw: Decimal | None = None
    capacity_min_inclusive: bool | None = None
    capacity_max_inclusive: bool | None = None


class ManagerInstallationStandardTariffList(BaseModel):
    price_book_revision: int | None = None
    items: list[ManagerInstallationStandardTariff] = Field(default_factory=list)


class ManagerInstallationStandardSuggestionsPayload(BaseModel):
    product_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(max_length=100)


class ManagerInstallationStandardSuggestion(BaseModel):
    product_id: int
    tariff: ManagerInstallationStandardTariff


class ManagerInstallationStandardSuggestionsResponse(BaseModel):
    items: list[ManagerInstallationStandardSuggestion] = Field(default_factory=list)


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
    quantity: int = 1
    description: str | None = None


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
    quantity: int = 1
    description: str | None = None


class ManagerInstallationPreviewResponse(InstallationPreviewResponse):
    collapsed_lines: list[ManagerInstallationPreviewLine] = Field(default_factory=list)
    detailed_lines: list[ManagerInstallationPreviewLine] = Field(default_factory=list)
