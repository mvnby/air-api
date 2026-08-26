from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    SENT = "sent"
    SIGNED = "signed"
    VOID = "void"
    REPLACED = "replaced"


class DocumentLifecycleError(ValueError):
    pass


_ALLOWED_TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.DRAFT: frozenset({DocumentStatus.ISSUED}),
    DocumentStatus.ISSUED: frozenset(
        {
            DocumentStatus.SENT,
            DocumentStatus.SIGNED,
            DocumentStatus.VOID,
            DocumentStatus.REPLACED,
        }
    ),
    DocumentStatus.SENT: frozenset(
        {DocumentStatus.SIGNED, DocumentStatus.VOID, DocumentStatus.REPLACED}
    ),
    DocumentStatus.SIGNED: frozenset({DocumentStatus.VOID, DocumentStatus.REPLACED}),
    DocumentStatus.VOID: frozenset(),
    DocumentStatus.REPLACED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class DocumentLifecycleState:
    status: DocumentStatus = DocumentStatus.DRAFT
    issued_at: datetime | None = None
    sent_at: datetime | None = None
    signed_at: datetime | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None
    replacement_document_id: int | None = None


def transition_document(
    state: DocumentLifecycleState,
    target: DocumentStatus,
    *,
    at: datetime | None = None,
    void_reason: str | None = None,
    replacement_document_id: int | None = None,
) -> DocumentLifecycleState:
    """Return a new valid lifecycle state without mutating persistence objects."""

    if target == state.status:
        return state
    if target not in _ALLOWED_TRANSITIONS[state.status]:
        raise DocumentLifecycleError(
            f"Cannot transition document from {state.status} to {target}"
        )

    changed_at = at or datetime.now(timezone.utc)
    if target == DocumentStatus.ISSUED:
        return replace(state, status=target, issued_at=changed_at)
    if target == DocumentStatus.SENT:
        return replace(state, status=target, sent_at=changed_at)
    if target == DocumentStatus.SIGNED:
        return replace(state, status=target, signed_at=changed_at)
    if target == DocumentStatus.VOID:
        normalized_reason = (void_reason or "").strip()
        if not normalized_reason:
            raise DocumentLifecycleError("Void reason is required")
        return replace(
            state,
            status=target,
            voided_at=changed_at,
            void_reason=normalized_reason,
        )
    if target == DocumentStatus.REPLACED:
        if replacement_document_id is None or replacement_document_id <= 0:
            raise DocumentLifecycleError("Replacement document id is required")
        return replace(
            state,
            status=target,
            replacement_document_id=replacement_document_id,
        )
    raise DocumentLifecycleError(f"Unsupported document status: {target}")
