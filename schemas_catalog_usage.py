"""Finite, anonymous vocabulary for the voluntary catalog-workspace pilot."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CatalogUsageLayoutVersion = Literal["catalog_workspace_v1"]
CatalogUsageDevice = Literal["mobile", "tablet", "desktop"]
CatalogUsageAction = Literal[
    "product_open", "filter_apply", "filter_zero_results", "edit_basics",
    "edit_pricing", "edit_specifications", "edit_gallery", "edit_features",
    "bulk_edit", "gallery_quick_exit", "media_load",
]
CatalogUsageOutcome = Literal["success", "cancelled", "failed", "zero_results", "quick_exit"]
CatalogUsageDurationBucket = Literal["none", "under_1s", "1_3s", "3_10s", "10_30s", "over_30s"]


class CatalogUsageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: CatalogUsageDevice
    action: CatalogUsageAction
    outcome: CatalogUsageOutcome
    duration_bucket: CatalogUsageDurationBucket = "none"


class CatalogUsageBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout_version: CatalogUsageLayoutVersion = "catalog_workspace_v1"
    # The client sends only after its account-local pilot opt-in. This is not an identifier.
    pilot_opt_in: Literal[True] = True
    events: list[CatalogUsageEvent] = Field(min_length=1, max_length=25)


class CatalogUsageAccepted(BaseModel):
    accepted: int


class CatalogUsageDailyItem(CatalogUsageEvent):
    day: date
    layout_version: CatalogUsageLayoutVersion
    count: int


class CatalogUsageReport(BaseModel):
    days: int
    since: date
    through: date
    timezone: Literal["Europe/Minsk"] = "Europe/Minsk"
    items: list[CatalogUsageDailyItem]
