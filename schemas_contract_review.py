from pydantic import BaseModel, Field


class ContractRisk(BaseModel):
    topic: str = Field(max_length=80)
    clause: str = Field(max_length=100)
    page: int | None = Field(default=None, ge=1)
    quote: str = Field(max_length=500)
    concern: str = Field(max_length=600)
    proposal: str = Field(max_length=600)


class ContractReviewResponse(BaseModel):
    attachment_id: int
    filename: str
    content_sha256: str
    model: str
    pages: int | None
    risks: list[ContractRisk]
    note: str


class OriginalEmailAttachmentItem(BaseModel):
    position: int
    filename: str
    size_bytes: int
    content_type: str


class OriginalEmailAttachmentList(BaseModel):
    items: list[OriginalEmailAttachmentItem]


class ContractReviewJobResponse(BaseModel):
    job_id: str
    status: str
    report: ContractReviewResponse | None = None
    error: str | None = None
