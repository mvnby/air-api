"""Additional work stays independent from the immutable original and live quote."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from docx import Document
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    OrderDocument,
    OrderProductLink,
    OrderServiceLink,
    Customer,
    CustomerType,
)
from models.tenancy import TenantScope
from modules.documents.application import (
    DocumentContextSelection,
    ManagedDocumentService,
)
from modules.documents.application.contract_amendments import list_bases
from modules.documents.application.draft_mutations import (
    ManagedDocumentDraftMutationService,
)
from modules.documents.application.errors import (
    ManagedDocumentConflictError,
    ManagedDocumentNotFoundError,
    ManagedDocumentGenerationError,
)
from modules.documents.domain.contract_amendment import ContractAmendmentTerms
from modules.documents.domain import (
    BusinessDocumentTerms,
    PaymentScheduleItem,
    ConsumerDocumentTerms,
)
from tests.integration.test_managed_document_lifecycle import (
    _seed,
    FakePdfConverter,
    FailingPdfConverter,
)


@pytest.fixture
async def amendment_db(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session


def terms(amount="250.00"):
    return ContractAmendmentTerms(
        works=[
            dict(
                title="Закладка межблочных коммуникаций для кондиционера",
                quantity="1",
                unit="компл.",
                unit_price=amount,
            )
        ],
        equipment="Тестовый кондиционер",
    )


async def setup(db, path, kind="contract"):
    scope, order, issuer, storage, artifacts = await _seed(db, path, document_type=kind)
    line = (
        await db.scalars(
            select(OrderProductLink).where(OrderProductLink.order_id == order.id)
        )
    ).one()
    line.price = Decimal("4160.00")
    if kind == "b2c_supply_installation_act":
        line.price = Decimal("4060.00")
        db.add(
            OrderServiceLink(
                order_id=order.id,
                proposal_id=line.proposal_id,
                title="Первоначальные монтаж и пусконаладка",
                quantity=1,
                price=Decimal("100.00"),
            )
        )
    # Synthetic requisites only. Freeze them in the original; later CRM edits
    # must not silently change the parties of the amendment.
    if kind == "b2c_supply_installation_act":
        customer = await db.get(Customer, order.customer_id)
        customer.type = CustomerType.individual
        customer.name = "Тестов Клиент Тестович"
        customer.full_legal_name = None
        customer.inn = customer.bank_name = customer.iban = customer.bic = None
        customer.signing_mode = "self"
        db.add(customer)
    if kind == "contract":
        customer = await db.get(Customer, order.customer_id)
        customer.signer_name = "Клиентов Клиент Тестович"
        customer.signer_position = "директор"
        customer.acting_basis = "Устав"
        customer.legal_address = "Тестовый адрес клиента"
        customer.inn = "000000002"
        customer.bank_name = "Тестовый банк клиента"
        customer.iban = "TEST-CUSTOMER-ACCOUNT"
        customer.bic = "TESTBANK"
        db.add(customer)
    issuer.requisites = {
        "signer_position": "директор",
        "acting_basis": "Устав",
        "bank_name": "Тестовый банк",
        "iban": "TEST-SELLER-ACCOUNT",
        "bic": "TESTBANK",
        "city": "Тестовый город",
        "signer_name": "Тестов Тест Тестович",
        "legal_address": "Тестовый адрес",
        "offer_url": "https://example.test/offer",
        "offer_version": "1",
        "offer_published_on": "01.11.2026",
    }
    db.add_all([line, issuer])
    await db.commit()
    basis = await ManagedDocumentService.create_draft(
        db,
        tenant_scope=scope,
        selection=DocumentContextSelection(
            order_id=order.id,
            document_type=kind,
            legal_entity_id=issuer.id,
            issue_date=date(2026, 11, 1),
            consumer_terms=ConsumerDocumentTerms() if kind != "contract" else None,
            business_terms=BusinessDocumentTerms(
                contract_scenario="supply_installation",
                payment_schedule=(
                    PaymentScheduleItem(
                        share_percent=Decimal("100"), due_event="before_work"
                    ),
                ),
            )
            if kind == "contract"
            else None,
        ),
        template_storage=storage,
    )
    await ManagedDocumentService.issue(
        db,
        tenant_scope=scope,
        document_id=basis.id,
        template_storage=storage,
        artifact_storage=artifacts,
        pdf_converter=FakePdfConverter(),
    )
    return scope, order, issuer, storage, artifacts, basis, line


async def draft(db, facts, amount="250.00", *, replacing=None):
    scope, order, issuer, storage, _, basis, _ = facts
    bases = await list_bases(db, scope=scope, order_id=order.id)
    return await ManagedDocumentService.create_draft(
        db,
        tenant_scope=scope,
        template_storage=storage,
        replaces_document_id=replacing,
        selection=DocumentContextSelection(
            order_id=order.id,
            document_type="contract_amendment",
            legal_entity_id=issuer.id,
            issue_date=date(2026, 11, 10),
            base_document_id=basis.id,
            amendment_terms=None if replacing else terms(amount),
            amendment_basis_revision=bases[0]["revision"],
        ),
    )


async def issue(db, facts, doc, converter=None):
    scope, _, _, storage, artifacts, _, _ = facts
    return await ManagedDocumentService.issue(
        db,
        tenant_scope=scope,
        document_id=doc.id,
        template_storage=storage,
        artifact_storage=artifacts,
        pdf_converter=converter or FakePdfConverter(),
    )


@pytest.mark.asyncio
async def test_frozen_original_date_edit_and_native_artifacts(amendment_db, tmp_path):
    db = amendment_db
    facts = await setup(db, tmp_path)
    scope, order, issuer, storage, artifacts, basis, line = facts
    original = deepcopy(basis.render_snapshot)
    old_artifacts = [
        a.id
        for a in await ManagedDocumentService.list_artifacts(
            db, tenant_scope=scope, document_id=basis.id
        )
    ]
    line.price = Decimal("9999.00")
    db.add(line)
    await db.commit()
    doc = await draft(db, facts)
    assert basis.status == "issued" and basis.render_snapshot == original
    values = doc.render_snapshot["values"]
    assert (
        values["totals.amount"],
        values["amendment.original_amount"],
        values["amendment.new_total"],
    ) == ("250.00", "4160.00", "4410.00")
    assert len(doc.render_snapshot["table_rows"]["lines"]) == 1
    assert "аванс" not in values["amendment.payment_terms"].lower()
    assert "после приёмки" not in values["amendment.payment_terms"].lower()
    assert (
        doc.base_document_id == basis.id
        and doc.replaces_document_id is None
        and doc.proposal_id is None
    )
    assert (
        doc.status == "draft" and doc.signed_at is None and doc.official_number is None
    )
    assert (await list_bases(db, scope=scope, order_id=order.id))[0][
        "agreed_total"
    ] == "4160.00"
    from modules.documents.application.draft_preview import (
        ManagedDocumentDraftPreviewService,
    )
    from modules.documents.application.customer_readiness import (
        check_saved_document_readiness,
    )

    readiness = await check_saved_document_readiness(
        db, tenant_scope=scope, document=doc, template_storage=storage
    )
    assert readiness["checked"] and readiness["can_issue"]

    class CapturePdf(FakePdfConverter):
        def convert_docx(self, content, *, filename="preview.docx"):
            (tmp_path / "amendment-preview.docx").write_bytes(content)
            return super().convert_docx(content, filename=filename)

    await ManagedDocumentDraftPreviewService.render_pdf(
        db,
        tenant_scope=scope,
        document_id=doc.id,
        template_storage=storage,
        artifact_storage=artifacts,
        pdf_converter=CapturePdf(),
    )
    before = deepcopy(doc.render_snapshot)
    parameters = await ManagedDocumentDraftMutationService.get(
        db, tenant_scope=scope, document_id=doc.id
    )
    await ManagedDocumentDraftMutationService.update(
        db,
        tenant_scope=scope,
        document_id=doc.id,
        expected_revision=parameters["revision"],
        changes={"issue_date": "2026-11-11"},
    )
    assert doc.render_snapshot["table_rows"] == before["table_rows"]
    assert doc.render_snapshot["meta"]["amendment"] == before["meta"]["amendment"]
    assert (
        doc.render_snapshot["meta"]["draft_parameters"]["amendment_terms"]
        == before["meta"]["draft_parameters"]["amendment_terms"]
    )
    with pytest.raises(ManagedDocumentConflictError, match="изменены"):
        await ManagedDocumentDraftMutationService.update(
            db,
            tenant_scope=scope,
            document_id=doc.id,
            expected_revision=parameters["revision"],
            changes={"issue_date": "2026-11-12"},
        )
    released = await issue(db, facts, doc)
    assert doc.status == "issued" and doc.signed_at is None
    assert (await list_bases(db, scope=scope, order_id=order.id))[0][
        "agreed_total"
    ] == "4410.00"
    artifact = next(a for a in released.artifacts if a.kind == "rendered_docx")
    content = await artifacts.read(ManagedDocumentService.stored_artifact(artifact))
    (tmp_path / "amendment-issued.docx").write_bytes(content)
    rendered = Document(BytesIO(content))
    text = "\n".join(p.text for p in rendered.paragraphs) + "\n".join(
        c.text for t in rendered.tables for row in t.rows for c in row.cells
    )
    for expected in (
        "4160.00",
        "250.00",
        "4410.00",
        "Закладка межблочных",
        "Тестов Тест Тестович",
        basis.render_snapshot["values"]["document.official_full_number"],
    ):
        assert expected in text
    assert basis.render_snapshot == original and basis.status == "issued"
    assert old_artifacts == [
        a.id
        for a in await ManagedDocumentService.list_artifacts(
            db, tenant_scope=scope, document_id=basis.id
        )
    ]


@pytest.mark.asyncio
async def test_two_drafts_second_agreement_and_replacement_count_once(
    amendment_db, tmp_path
):
    db = amendment_db
    facts = await setup(db, tmp_path)
    scope, order, _, _, _, basis, _ = facts
    first = await draft(db, facts)
    stale = await draft(db, facts, "100.00")
    await issue(db, facts, first)
    with pytest.raises(ManagedDocumentConflictError, match="изменились"):
        await issue(db, facts, stale)
    assert stale.official_number is None and stale.status == "draft"
    second = await draft(db, facts, "100.00")
    assert second.render_snapshot["values"]["amendment.new_total"] == "4510.00"
    await issue(db, facts, second)
    revision = await draft(db, facts, replacing=first.id)
    assert revision.render_snapshot["values"]["amendment.new_total"] == "4510.00"
    assert (
        revision.render_snapshot["meta"]["draft_parameters"]["amendment_terms"]
        == first.render_snapshot["meta"]["draft_parameters"]["amendment_terms"]
    )
    assert (await list_bases(db, scope=scope, order_id=order.id))[0][
        "agreed_total"
    ] == "4510.00"
    await issue(db, facts, revision)
    await issue(db, facts, revision)
    assert (
        first.status == "replaced"
        and revision.status == "issued"
        and basis.status == "issued"
    )
    assert (await list_bases(db, scope=scope, order_id=order.id))[0][
        "agreed_total"
    ] == "4510.00"
    await ManagedDocumentService.void(
        db, tenant_scope=scope, document_id=second.id, reason="Тестовая отмена"
    )
    assert (await list_bases(db, scope=scope, order_id=order.id))[0][
        "agreed_total"
    ] == "4410.00"


@pytest.mark.asyncio
async def test_generation_retry_and_change_during_render(amendment_db, tmp_path):
    db = amendment_db
    facts = await setup(db, tmp_path)
    doc = await draft(db, facts)
    with pytest.raises(ManagedDocumentGenerationError):
        await issue(db, facts, doc, FailingPdfConverter())
    number = doc.official_number
    assert number and doc.status == "draft"
    await issue(db, facts, doc)
    assert doc.official_number == number and doc.status == "issued"


@pytest.mark.asyncio
async def test_explicit_basis_tenant_and_stale_revision(amendment_db, tmp_path):
    db = amendment_db
    facts = await setup(db, tmp_path)
    scope, order, issuer, storage, _, basis, _ = facts
    bases = await list_bases(db, scope=scope, order_id=order.id)
    with pytest.raises(ManagedDocumentConflictError, match="выберите"):
        await ManagedDocumentService.create_draft(
            db,
            tenant_scope=scope,
            template_storage=storage,
            selection=DocumentContextSelection(
                order_id=order.id,
                document_type="contract_amendment",
                legal_entity_id=issuer.id,
                issue_date=date(2026, 11, 10),
                amendment_terms=terms(),
            ),
        )
    with pytest.raises(ManagedDocumentConflictError, match="изменились"):
        await ManagedDocumentService.create_draft(
            db,
            tenant_scope=scope,
            template_storage=storage,
            selection=DocumentContextSelection(
                order_id=order.id,
                document_type="contract_amendment",
                legal_entity_id=issuer.id,
                issue_date=date(2026, 11, 10),
                amendment_terms=terms(),
                base_document_id=basis.id,
                amendment_basis_revision="0" * 64,
            ),
        )
    with pytest.raises(ManagedDocumentNotFoundError):
        await list_bases(
            db,
            scope=TenantScope(tenant_id=scope.tenant_id, storefront_id=99999),
            order_id=order.id,
        )


@pytest.mark.asyncio
async def test_second_finalization_rechecks_after_render(
    amendment_db, db_engine, tmp_path, monkeypatch
):
    import modules.documents.application.lifecycle_service as lifecycle

    db = amendment_db
    facts = await setup(db, tmp_path)
    first = await draft(db, facts)
    second = await draft(db, facts, "100.00")
    original_render = lifecycle.render_and_store_issued_artifacts
    changed = False

    async def render(**kwargs):
        nonlocal changed
        result = await original_render(**kwargs)
        if not changed:
            changed = True
            async with AsyncSession(db_engine, expire_on_commit=False) as other_db:
                other_second = await other_db.get(OrderDocument, second.id)
                await issue(other_db, facts, other_second)
        return result

    monkeypatch.setattr(lifecycle, "render_and_store_issued_artifacts", render)
    with pytest.raises(ManagedDocumentConflictError, match="изменились"):
        await issue(db, facts, first)
    assert first.status == "draft" and first.official_number
    order_id = facts[1].id
    await db.rollback()
    assert (await list_bases(db, scope=facts[0], order_id=order_id))[0][
        "agreed_total"
    ] == "4260.00"


@pytest.mark.asyncio
async def test_supply_installation_contract_and_multiple_choices(
    amendment_db, tmp_path
):
    db = amendment_db
    facts = await setup(db, tmp_path, kind="b2c_supply_installation_act")
    scope, order, issuer, storage, _, basis, line = facts
    original = deepcopy(basis.render_snapshot)
    assert len(original["table_rows"]["lines"]) == 2
    doc = await draft(db, facts)
    assert doc.render_snapshot["values"]["amendment.new_total"] == "4410.00"
    assert len(doc.render_snapshot["table_rows"]["lines"]) == 1
    assert (
        "пусконаладка"
        not in doc.render_snapshot["table_rows"]["lines"][0]["line.title"]
    )
    released = await issue(db, facts, doc)
    artifact = next(a for a in released.artifacts if a.kind == "rendered_docx")
    content = await facts[4].read(ManagedDocumentService.stored_artifact(artifact))
    (tmp_path / "amendment-individual.docx").write_bytes(content)
    rendered = Document(BytesIO(content))
    text = "\n".join(p.text for p in rendered.paragraphs)
    assert "Тестов Клиент Тестович ____________________" in text
    client_requisites = text.split("Клиент: Тестов Клиент Тестович")[-1]
    assert "УНП" not in client_requisites and "БИК" not in client_requisites
    assert "Клиент действует от собственного имени" in text
    assert "Клиент: представитель" not in text
    assert basis.render_snapshot == original and basis.status == "issued"
    another_basis = await ManagedDocumentService.create_draft(
        db,
        tenant_scope=scope,
        template_storage=storage,
        selection=DocumentContextSelection(
            order_id=order.id,
            legal_entity_id=issuer.id,
            document_type="b2c_supply_installation_act",
            issue_date=date(2026, 11, 2),
            consumer_terms=ConsumerDocumentTerms(),
        ),
    )
    await issue(db, facts, another_basis)
    choices = await list_bases(db, scope=scope, order_id=order.id)
    assert len(choices) == 2 and {item["document_id"] for item in choices} == {
        basis.id,
        another_basis.id,
    }
    assert all(
        item["number"] and item["date"] and item["status"] == "issued"
        for item in choices
    )


@pytest.mark.asyncio
async def test_missing_basis_date_is_visible_and_not_guessed(amendment_db, tmp_path):
    from modules.documents.application.customer_readiness import (
        check_saved_document_readiness,
    )

    db = amendment_db
    facts = await setup(db, tmp_path)
    basis = facts[5]
    snapshot = deepcopy(basis.render_snapshot)
    snapshot["values"]["document.issued_on"] = ""
    basis.render_snapshot = snapshot
    db.add(basis)
    await db.commit()
    doc = await draft(db, facts)
    assert doc.render_snapshot["values"]["basis.date"] == ""
    readiness = await check_saved_document_readiness(
        db, tenant_scope=facts[0], document=doc, template_storage=facts[3]
    )
    assert any(f["field"] == "basis.date" for f in readiness["missing_fields"])
    assert not readiness["can_issue"]
    with pytest.raises(ManagedDocumentConflictError, match="реквизиты"):
        await issue(db, facts, doc)
    assert doc.official_number is None


@pytest.mark.asyncio
async def test_manager_replacement_readiness_inherits_saved_amendment(
    amendment_db, tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from modules.documents.api.managed_document_readiness import (
        check_managed_document_readiness,
    )
    from modules.documents.api.schemas import ManagedDocumentDraftPayload
    import modules.documents.api.managed_document_readiness as api
    import importlib
    composition = importlib.import_module("modules.documents.api.router")

    db = amendment_db
    facts = await setup(db, tmp_path)
    scope, order, issuer, storage, _, basis, _ = facts
    original = await draft(db, facts)
    await issue(db, facts, original)
    monkeypatch.setattr(api, "PrivateTemplateSourceStorage", lambda _: storage)
    monkeypatch.setattr(composition, "get_private_attachment_storage", lambda: object())
    # A replacement is based on saved facts, even when the caller supplies no
    # current proposal, basis revision or repeated work/conditions.
    payload = ManagedDocumentDraftPayload(
        document_type="contract_amendment",
        legal_entity_id=issuer.id,
        issue_date=date(2026, 11, 12),
        replaces_document_id=original.id,
    )
    readiness = await check_managed_document_readiness(
        order.id, payload, session=db, auth=SimpleNamespace(tenant_scope=lambda: scope)
    )
    assert readiness["checked"] and readiness["can_issue"]
    replacement = await ManagedDocumentService.create_draft(
        db,
        tenant_scope=scope,
        template_storage=storage,
        replaces_document_id=original.id,
        selection=DocumentContextSelection(
            order_id=order.id,
            document_type="contract_amendment",
            legal_entity_id=issuer.id,
            issue_date=payload.issue_date,
        ),
    )
    assert replacement.base_document_id == basis.id
    assert replacement.render_snapshot["values"]["amendment.new_total"] == "4410.00"
    assert (
        replacement.render_snapshot["meta"]["draft_parameters"]["amendment_terms"]
        == original.render_snapshot["meta"]["draft_parameters"]["amendment_terms"]
    )
    assert original.status == "issued"
