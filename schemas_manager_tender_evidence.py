"""Manager background verification of selected source documents."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas_connector_tender_review import AnalyzedTenderFile
from schemas_tender_qualification import TenderExtractionStatus, TenderQualificationFact


class ManagerTenderEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(min_length=1, max_length=8)


class ManagerTenderEvidenceReport(BaseModel):
    documents: list[AnalyzedTenderFile]
    unselected_count: int
    document_coverage_complete: bool
    analysis_status: TenderExtractionStatus
    findings: list[TenderQualificationFact]


class ManagerTenderEvidenceJob(BaseModel):
    job_id: str
    status: Literal["reading", "analyzing", "completed", "failed"]
    processed: int
    total: int
    report: ManagerTenderEvidenceReport | None = None
    error: str | None = None
