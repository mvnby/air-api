"""Incoming queue contracts; customer orders and raw leads keep their identities."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas_common import Meta

RefusalReason = Literal["profile", "region", "terms", "capacity", "unclear", "other"]
ArchiveOutcome = Literal["refusal", "spam", "duplicate", "deadline_expired", "legacy_lost", "linked"]


class LeadsCounterResponse(BaseModel):
    count: int
    has_new: bool
    pending_count: int = 0
    unread_count: int = 0


class LeadsInboxTenderResponse(BaseModel):
    source: str | None = None
    url: str | None = None
    deadline_at: datetime | None = None
    reason: str | None = None
    profile_name: str | None = None


class LeadsInboxArchiveResponse(BaseModel):
    outcome: ArchiveOutcome
    reason: str | None = None
    note: str | None = None
    archived_at: datetime | None = None
    actor: str | None = None


class LeadsInboxHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    actor: str
    created_at: datetime
    note: str | None = None
    next_followup_at: datetime | None = None
    outcome: str | None = None
    reason: str | None = None


class InboxRelatedRequest(BaseModel):
    order_id: int
    title: str | None = None
    outcome: str | None = None
    reason: str | None = None
    note: str | None = None
    url: str


class LeadsInboxItemResponse(BaseModel):
    id: int
    entity_kind: Literal["order", "lead"] = "order"
    related_requests: list[InboxRelatedRequest] = Field(default_factory=list)
    status: str
    is_new: bool
    is_read: bool = False
    read_at: datetime | None = None
    source_kind: Literal["customer_request", "tender"] = "customer_request"
    title: str | None = None
    summary: str | None = None
    budget_amount: float | None = None
    budget_currency: str | None = None
    quantity: float | None = None
    location: str | None = None
    deadline_at: datetime | None = None
    archive: LeadsInboxArchiveResponse | None = None
    auto_archive_at: datetime | None = None
    linked_order_id: int | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    phone: str | None = None
    email: str | None = None
    source: str | None = None
    comment: str | None = None
    no_answer_at: datetime | None = None
    no_answer_count: int = 0
    next_followup_at: datetime | None = None
    source_created_at: datetime | None = None
    created_at: datetime
    customer_type: str | None = None
    customer_inn: str | None = None
    customer_full_legal_name: str | None = None
    customer_delivery_address: str | None = None
    object_type: str | None = None
    service_type: str | None = None
    equipment_class: str | None = None
    marketing_source: str | None = None
    attachment_count: int = 0
    tender: LeadsInboxTenderResponse | None = None
    commercial_terms_summary: list[str] = Field(default_factory=list)
    intake_state: Literal["needs_contact", "needs_details", "ready_for_review"] | None = None
    intake_version: int | None = None
    requested_time_text: str | None = None
    requested_at: datetime | None = None
    missing_fields: list[str] = Field(default_factory=list)


class LeadsInboxDetailResponse(LeadsInboxItemResponse):
    original_text: str | None = None
    original_text_truncated: bool = False
    history: list[LeadsInboxHistoryResponse] = Field(default_factory=list)


class LeadsInboxListResponse(BaseModel):
    items: list[LeadsInboxItemResponse]
    total: int
    meta: Meta
    pending_count: int = 0
    unread_count: int = 0
    source_counts: dict[str, int] = Field(default_factory=dict, description=
        "Counts across the selected scope, search and unread filter, before source filtering or pagination.")


class InboxReadPayload(BaseModel):
    is_read: bool


class InboxTenderPayload(BaseModel):
    is_tender: bool
    deadline_at: datetime | None = None
    source_url: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def validate_context(self):
        if self.deadline_at is not None and self.deadline_at.tzinfo is None:
            raise ValueError("Срок подачи должен включать часовой пояс")
        self.source_url = (self.source_url or "").strip() or None
        if self.source_url:
            try:
                parsed = urlsplit(self.source_url)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("Укажите ссылку http(s) на источник закупки")
            except ValueError as exc:
                raise ValueError("Укажите ссылку http(s) на источник закупки") from exc
        return self


class InboxArchivePayload(BaseModel):
    outcome: Literal["refusal", "spam", "duplicate"]
    reason: RefusalReason | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_reason(self):
        self.note = (self.note or "").strip() or None
        if self.outcome == "refusal" and self.reason is None:
            raise ValueError("Для отказа выберите причину")
        if self.outcome != "refusal" and self.reason is not None:
            raise ValueError("Причина отказа применима только к отказу")
        if self.reason == "other" and self.note is None:
            raise ValueError("Для другой причины укажите пояснение")
        return self


class InboxNoAnswerPayload(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    next_followup_at: datetime | None = None

    @model_validator(mode="after")
    def normalize(self):
        self.note = (self.note or "").strip() or None
        if self.next_followup_at is not None and self.next_followup_at.tzinfo is None:
            raise ValueError("Дата напоминания должна включать часовой пояс")
        return self
