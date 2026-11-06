"""One-room equipment and declared normal-installation sales estimates."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from schemas_catalog_accessories import PublicCatalogAccessory
from schemas_connector_catalog import CatalogProductDetail, CatalogSelectionInput
from schemas_connector_mcp import ConnectorInput
from schemas_installation_price_book import (
    InstallationExtraInput, InstallationInput, InstallationPreviewResponse,
)


class SalesInstallationInput(ConnectorInput):
    route_length_m: Decimal | None = Field(default=None, gt=0, le=1000, decimal_places=2)
    holes_by_type: dict[str, Decimal] | None = Field(default=None, description=(
        "Whole counts of declared wall penetrations. Native codes: through_thin = additional "
        "interior-wall passages up to 20 cm; through_thick = main-wall passages up to 80 cm; "
        "through_over_80 = walls thicker than 80 cm, requiring a manual quote; diamond = "
        "explicit diamond drilling, only if priced by the published tariff. Do not substitute "
        "diamond for a normal wall passage. Use null for unknown conditions, or {} only when "
        "no passages are required. State any preliminary assumptions explicitly."
    ))
    access: Literal["standard", "requires_assessment", "unknown"] = "unknown"
    extras: list[InstallationExtraInput] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def declared_work(self):
        if any(not item.strip() or len(item) > 500 for item in self.assumptions):
            raise ValueError("Assumptions must be nonblank and at most 500 characters")
        if len({extra.code for extra in self.extras}) != len(self.extras):
            raise ValueError("Installation extras must be unique")
        # Reuse the domain's whole-hole and stable-code validation, including
        # when some other site inputs have not yet been supplied.
        if self.holes_by_type is not None:
            InstallationInput(product_id=1, key="sales", route_length_m=0,
                              holes_by_type=self.holes_by_type)
        return self


class SalesSelectionInput(CatalogSelectionInput):
    quantity: Literal[1] = 1
    budget_byn: Decimal | None = Field(default=None, gt=0, le=10_000_000, decimal_places=2)
    budget_scope: Literal["total"] = "total"
    installation: SalesInstallationInput = Field(default_factory=SalesInstallationInput)
    accessory_product_ids: list[int] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_accessories(self):
        if any(value < 1 for value in self.accessory_product_ids) or \
                len(set(self.accessory_product_ids)) != len(self.accessory_product_ids):
            raise ValueError("Accessory IDs must be unique and positive")
        return self


class SalesPreviewInput(ConnectorInput):
    product_id: int = Field(gt=0)
    installation: SalesInstallationInput
    accessory_product_ids: list[int] = Field(default_factory=list, max_length=20)
    expected_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)

    @model_validator(mode="after")
    def unique_accessories(self):
        if any(value < 1 for value in self.accessory_product_ids) or \
                len(set(self.accessory_product_ids)) != len(self.accessory_product_ids):
            raise ValueError("Accessory IDs must be unique and positive")
        return self


class SalesSelectionOption(ConnectorInput):
    label: str
    product: CatalogProductDetail
    quantity: Literal[1] = 1
    image_url: str | None = None
    compatible_accessories: list[PublicCatalogAccessory] = Field(default_factory=list)
    selected_accessories: list[PublicCatalogAccessory] = Field(default_factory=list)
    equipment_total_byn: Decimal
    accessories_total_byn: Decimal
    installation_total_byn: Decimal
    total_byn: Decimal
    currency: Literal["BYN"] = "BYN"
    installation_input: SalesInstallationInput
    installation: InstallationPreviewResponse
    calculation_fingerprint: str
    price_kind: Literal["estimate"] = "estimate"
    assumptions: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class SalesSelectionResult(ConnectorInput):
    status: Literal["ready", "needs_input", "not_ready", "no_matches"]
    checked_at: datetime
    options: list[SalesSelectionOption] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    matching_products: int = 0
    excluded_reasons: dict[str, int] = Field(default_factory=dict)
    message_text: str
    installation_included: Literal[True] = True
