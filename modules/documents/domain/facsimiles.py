"""Validated positions on the displayed (cropped and rotated) PDF page."""

from pydantic import BaseModel, ConfigDict, Field


class FacsimileImagePlacement(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    page_number: int = Field(ge=1, le=100)
    x_mm: float = Field(ge=0, le=1000)
    y_mm: float = Field(ge=0, le=1000)
    width_mm: float = Field(gt=0, le=500)


class FacsimilePlacement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signature: FacsimileImagePlacement
    seal: FacsimileImagePlacement


class FacsimilePdfPlacement(FacsimilePlacement):
    """Bind a visual edit to the exact PDF, assets and copy that were displayed."""

    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_signed_artifact_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    signature_asset_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    seal_asset_id: str = Field(pattern=r"^[0-9a-f]{32}$")
