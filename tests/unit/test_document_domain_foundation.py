from datetime import date, datetime, timezone

import pytest
from sqlalchemy import CheckConstraint, Date, ForeignKeyConstraint, UniqueConstraint
from sqlmodel import SQLModel

import models  # noqa: F401
from modules.documents.domain import (
    DocumentLifecycleError,
    DocumentLifecycleState,
    DocumentNumberScope,
    DocumentStatus,
    EffectiveDocumentNumberPolicy,
    new_internal_reference,
    transition_document,
)


def test_document_lifecycle_is_immutable_and_enforces_terminal_states() -> None:
    issued_at = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    draft = DocumentLifecycleState()
    issued = transition_document(draft, DocumentStatus.ISSUED, at=issued_at)
    sent = transition_document(issued, DocumentStatus.SENT, at=issued_at)
    signed = transition_document(sent, DocumentStatus.SIGNED, at=issued_at)
    replaced = transition_document(
        signed,
        DocumentStatus.REPLACED,
        replacement_document_id=42,
    )

    assert draft.status == DocumentStatus.DRAFT
    assert issued.issued_at == issued_at
    assert sent.sent_at == issued_at
    assert signed.signed_at == issued_at
    assert replaced.replacement_document_id == 42
    with pytest.raises(DocumentLifecycleError):
        transition_document(
            replaced, DocumentStatus.VOID, void_reason="late correction"
        )


def test_document_lifecycle_requires_void_reason_and_replacement_identity() -> None:
    issued = DocumentLifecycleState(status=DocumentStatus.ISSUED)

    with pytest.raises(DocumentLifecycleError, match="Void reason"):
        transition_document(issued, DocumentStatus.VOID)
    with pytest.raises(DocumentLifecycleError, match="Replacement document id"):
        transition_document(issued, DocumentStatus.REPLACED)

    voided = transition_document(
        issued, DocumentStatus.VOID, void_reason="  duplicate  "
    )
    assert voided.void_reason == "duplicate"


def test_number_scope_normalization_and_internal_reference_are_not_official_numbers() -> (
    None
):
    scope = DocumentNumberScope(
        tenant_id=1,
        legal_entity_id=2,
        document_type=" Invoice ",
        series="СФ-2026-",
        period_key=" 2026 ",
    ).normalized()

    assert scope.document_type == "invoice"
    assert scope.period_key == "2026"
    first = new_internal_reference()
    second = new_internal_reference()
    assert first.startswith("doc_")
    assert first != second
    assert "СФ" not in first


def test_per_basis_period_key_respects_persisted_sequence_limit() -> None:
    policy = EffectiveDocumentNumberPolicy(
        document_type="act",
        series="А-",
        period_mode="per_basis",
    )

    assert policy.period_key(date(2026, 8, 26), basis_key="c" * 32) == "c" * 32
    with pytest.raises(ValueError, match="Basis is required"):
        policy.period_key(date(2026, 8, 26), basis_key="c" * 33)


def test_document_metadata_has_scoped_identity_and_version_guards() -> None:
    order_document = SQLModel.metadata.tables["order_document"]
    artifact = SQLModel.metadata.tables["document_artifact"]
    template = SQLModel.metadata.tables["document_template"]
    version = SQLModel.metadata.tables["document_template_version"]
    sequence = SQLModel.metadata.tables["document_number_sequence"]
    policy = SQLModel.metadata.tables["document_number_policy"]
    reservation = SQLModel.metadata.tables["document_number_reservation"]

    assert order_document.c.tenant_id.nullable is True
    assert template.c.tenant_id.nullable is True
    assert template.c.google_template_id.nullable is True
    assert order_document.c.google_file_id.nullable is True
    assert isinstance(order_document.c.official_date.type, Date)
    assert "official_period_key" in order_document.c
    assert any(
        index.name == "uq_order_document_official_identity" and index.unique
        for index in order_document.indexes
    )
    assert any(
        index.name == "uq_order_document_id_tenant_legal_entity" and index.unique
        for index in order_document.indexes
    )
    assert any(
        index.name == "uq_order_document_active_replacement" and index.unique
        for index in order_document.indexes
    )
    assert any(
        index.name == "uq_document_template_version_active" and index.unique
        for index in version.indexes
    )
    assert any(
        index.name == "uq_document_artifact_authoritative_kind" and index.unique
        for index in artifact.indexes
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_document_number_sequence_scope"
        for constraint in sequence.constraints
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_document_number_policy_scope"
        for constraint in policy.constraints
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_document_number_reservation_idempotency"
        for constraint in reservation.constraints
    )
    assert any(
        isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_document_number_reservation_document_scope"
        and tuple(constraint.column_keys)
        == ("document_id", "tenant_id", "legal_entity_id")
        for constraint in reservation.constraints
    )
    for table, constraint_name in (
        (order_document, "ck_order_document_status_valid"),
        (order_document, "ck_order_document_managed_scope_complete"),
        (version, "ck_document_template_version_status_valid"),
        (reservation, "ck_document_number_reservation_status_valid"),
    ):
        assert any(
            isinstance(constraint, CheckConstraint)
            and constraint.name == constraint_name
            for constraint in table.constraints
        )
