"""Visual facsimile editor API contract."""

from pydantic import BaseModel

from modules.documents.domain.facsimiles import FacsimilePdfPlacement, FacsimilePlacement


class DocumentFacsimilePdfPayload(FacsimilePdfPlacement):
    pass


class FacsimilePreviewPage(BaseModel):
    page_number: int
    width_mm: float
    height_mm: float


class FacsimilePreviewAsset(BaseModel):
    asset_id: str
    width_px: int
    height_px: int


class DocumentFacsimilePreviewResponse(BaseModel):
    document_id: int
    source_checksum_sha256: str
    signed_artifact_id: str | None
    can_save: bool
    pages: list[FacsimilePreviewPage]
    signature: FacsimilePreviewAsset
    seal: FacsimilePreviewAsset
    placement: FacsimilePlacement
