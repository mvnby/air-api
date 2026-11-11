"""Consumer identity requirements and the mutation-free native issuance boundary."""

from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

from docx import Document
import pytest

from modules.documents.application import customer_readiness as readiness
from modules.documents.application.artifact_helpers import build_render_inputs, prepare_artifact_download
from modules.documents.application.errors import ManagedDocumentConflictError
from modules.documents.application.lifecycle_service import ManagedDocumentService
from modules.documents.domain import B2C_NATIVE_DOCUMENT_TYPES
from modules.documents.domain.party import party_conditions
from modules.documents.infrastructure.renderers import NativeDocxRenderer


def source_bytes():
    document = Document()
    for text in (
        "Заказчик: {{ customer.full_name }}",
        "Адрес выполнения работ: {{ order.object_address }}",
        "Телефон: {{ customer.phone }}",
    ):
        document.add_paragraph(text)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def snapshot(document_type, **values):
    return {
        "values": {"document.type": document_type, "customer.entity_type": "individual",
                   "customer.signing_mode": "self", **values},
        "conditions": party_conditions("customer", entity_type="individual", signing_mode="self"),
        "meta": {"customer_readiness": {"checked": False, "missing_fields": [], "can_issue": True}},
    }


def template_version():
    return SimpleNamespace(id=4, tenant_id=3, doc_type=""), SimpleNamespace(
        version=1, source_filename="consumer.docx", source_storage_key="frozen-source",
        checksum_sha256="sha", placeholder_schema={"fields": [
            "customer.full_name", "order.object_address", "customer.phone",
        ]},
    )


@pytest.mark.parametrize("document_type", sorted(B2C_NATIVE_DOCUMENT_TYPES))
@pytest.mark.parametrize("missing", [None, "", "  \n\t", "____________ (ФИО)", "—", "____. __ — ---", "{{ customer.full_name }}"])
def test_consumer_missing_identity_and_site_block_issue_but_phone_stays_advisory(document_type, missing):
    frozen = snapshot(document_type, **{"customer.full_name": missing, "order.object_address": missing})
    original = deepcopy(frozen)
    result = readiness.snapshot_customer_readiness(frozen, source=source_bytes(), document_type=document_type)
    assert result["checked"] and not result["can_issue"]
    assert {item["field"]: item["critical"] for item in result["missing_fields"]} == {
        "customer.full_name": True, "order.object_address": True, "customer.phone": False,
    }
    assert next(item["label"] for item in result["missing_fields"] if item["field"] == "customer.full_name") == "ФИО клиента"
    assert frozen == original


@pytest.mark.parametrize("document_type", sorted(B2C_NATIVE_DOCUMENT_TYPES))
@pytest.mark.parametrize("field", ["customer.full_name", "order.object_address"])
def test_each_printed_consumer_identity_fact_is_required_independently(document_type, field):
    values = {"customer.full_name": "Петров Пётр Петрович", "order.object_address": "г. Витебск, ул. Мира, 1", "customer.phone": "+375290000001"}
    values[field] = ""
    result = readiness.snapshot_customer_readiness(snapshot(document_type, **values), source=source_bytes(), document_type=document_type)
    assert not result["can_issue"]
    assert [item["field"] for item in result["missing_fields"]] == [field]


@pytest.mark.parametrize("document_type", sorted(B2C_NATIVE_DOCUMENT_TYPES))
def test_complete_consumer_identity_can_issue_without_optional_phone_or_organization_details(document_type):
    result = readiness.snapshot_customer_readiness(
        snapshot(document_type, **{"customer.full_name": "Петров Пётр Петрович", "order.object_address": "г. Витебск, ул. Мира, 1"}),
        source=source_bytes(), document_type=document_type,
    )
    assert result["can_issue"]
    assert [item["field"] for item in result["missing_fields"]] == ["customer.phone"]


@pytest.mark.parametrize("document_type", sorted(B2C_NATIVE_DOCUMENT_TYPES))
def test_consumer_draft_render_has_handwriting_hints_without_mutating_frozen_facts(document_type):
    frozen = snapshot(document_type)
    original = deepcopy(frozen)
    template, version = template_version()
    template.doc_type = document_type
    render_template, context = build_render_inputs(template=template, version=version, source=source_bytes(), snapshot=frozen)
    output = Document(BytesIO(NativeDocxRenderer().render(render_template, context).content))
    text = "\n".join(p.text for p in output.paragraphs)
    assert "Заказчик: ____" in text and "ФИО клиента" in text
    assert "Адрес выполнения работ: ____" in text
    assert "Телефон: ____" in text
    assert "{{" not in text and frozen == original


@pytest.mark.asyncio
@pytest.mark.parametrize("document_type", sorted(B2C_NATIVE_DOCUMENT_TYPES))
async def test_actual_issue_and_preflight_reject_missing_consumer_before_numbering_or_storage(monkeypatch, document_type):
    frozen = snapshot(document_type)
    document = SimpleNamespace(
        id=7, status="draft", doc_type=document_type, internal_reference="draft-7",
        legal_entity_id=1, template_version_id=4, render_snapshot=frozen, replaces_document_id=None,
    )
    template, version = template_version()
    load = AsyncMock(return_value=(template, version))
    monkeypatch.setattr(readiness, "load_document_template_version", load)
    monkeypatch.setattr(ManagedDocumentService, "get_document", AsyncMock(return_value=document))
    monkeypatch.setattr(ManagedDocumentService, "_get_scoped_document", AsyncMock(return_value=document))
    templates = SimpleNamespace(read_persisted=AsyncMock(return_value=source_bytes()))

    class NoMutations:
        def __getattr__(self, name):
            raise AssertionError(f"Issuance must reject before accessing {name}")

    for issue in (False, True):
        original = deepcopy(document.__dict__)
        with pytest.raises(ManagedDocumentConflictError, match="Перед выпуском заполните данные.*ФИО клиента"):
            if issue:
                await ManagedDocumentService.issue(
                    NoMutations(), tenant_scope=SimpleNamespace(tenant_id=3), document_id=7,
                    template_storage=templates, artifact_storage=NoMutations(), pdf_converter=NoMutations(),
                )
            else:
                await ManagedDocumentService.validate_issue_customer_readiness(
                    NoMutations(), tenant_scope=SimpleNamespace(tenant_id=3), document_id=7, template_storage=templates,
                )
        assert document.__dict__ == original
    assert templates.read_persisted.await_count == 2


@pytest.mark.parametrize("document_type", sorted(B2C_NATIVE_DOCUMENT_TYPES))
def test_consumer_cached_critical_requirements_are_not_downgraded_to_legacy_advice(document_type):
    from modules.documents.api.managed_documents_artifacts import _cached_customer_readiness

    frozen = snapshot(document_type)
    expected = readiness.snapshot_customer_readiness(frozen, source=source_bytes(), document_type=document_type)
    frozen["meta"]["customer_readiness"] = deepcopy(expected)
    document = SimpleNamespace(doc_type=document_type, render_snapshot=frozen)
    assert _cached_customer_readiness(document).model_dump() == expected
    assert frozen["meta"]["customer_readiness"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("document_type", sorted(B2C_NATIVE_DOCUMENT_TYPES))
@pytest.mark.parametrize("status", ["issued", "sent", "signed"])
async def test_issued_consumer_results_and_download_bytes_are_reused_unchanged(monkeypatch, document_type, status):
    frozen = snapshot(document_type)
    document = SimpleNamespace(id=7, status=status, doc_type=document_type, render_snapshot=frozen)
    original = deepcopy(frozen)
    artifact = SimpleNamespace(kind="source_docx", order_document_id=7)
    artifacts = [artifact]
    monkeypatch.setattr(ManagedDocumentService, "get_document", AsyncMock(return_value=document))
    monkeypatch.setattr(ManagedDocumentService, "_get_scoped_document", AsyncMock(return_value=document))
    monkeypatch.setattr(ManagedDocumentService, "_artifacts", AsyncMock(return_value=artifacts))
    result = await ManagedDocumentService.issue(
        None, tenant_scope=SimpleNamespace(tenant_id=3), document_id=7,
        template_storage=None, artifact_storage=None, pdf_converter=None,
    )
    assert result.document is document and result.artifacts == (artifact,)
    assert await readiness.check_saved_document_readiness(
        None, tenant_scope=None, document=document, template_storage=None,
    ) == {"checked": False, "missing_fields": [], "can_issue": True}
    content = source_bytes()
    assert await prepare_artifact_download(
        None, tenant_scope=None, artifact=artifact, content=content, template_storage=None,
    ) is content
    assert document.render_snapshot == original
