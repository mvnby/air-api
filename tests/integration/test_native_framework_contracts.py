import asyncio
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from models import Customer, CustomerContract, DocumentNumberReservation, OrderDocument
from modules.documents.application import (
    DocumentContextSelection, ManagedDocumentConflictError, ManagedDocumentService,
)
from modules.documents.domain import BusinessDocumentTerms, PaymentScheduleItem
from tests.integration.test_managed_document_lifecycle import FakePdfConverter, FailingPdfConverter, _seed
from modules.documents.application.errors import ManagedDocumentGenerationError


def _selection(order, issuer, *, valid_until=date(2027, 4, 25)):
    return DocumentContextSelection(
        order_id=order.id, legal_entity_id=issuer.id, document_type="contract", issue_date=date(2026, 4, 25),
        document_role_type="executor_customer",
        business_terms=BusinessDocumentTerms(
            contract_scenario="framework", valid_until=valid_until,
            payment_schedule=(PaymentScheduleItem(Decimal("100"), "before_work"),),
        ),
    )


@pytest.mark.asyncio
async def test_framework_register_follows_issue_replacement_and_void(db, tmp_path):
    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path)
    create = dict(tenant_scope=scope, selection=_selection(order, issuer), template_storage=templates)
    issue = dict(tenant_scope=scope, template_storage=templates,
                 artifact_storage=artifacts, pdf_converter=FakePdfConverter())
    draft = await ManagedDocumentService.create_draft(db, **create)
    assert draft.render_snapshot["meta"]["customer_id"] == order.customer_id
    count = select(func.count()).select_from(CustomerContract)
    assert await db.scalar(count) == 0
    with pytest.raises(ManagedDocumentGenerationError):
        await ManagedDocumentService.issue(db, document_id=draft.id, **{**issue, "pdf_converter": FailingPdfConverter()})
    assert await db.scalar(count) == 0
    await ManagedDocumentService.issue(db, document_id=draft.id, **issue)
    await ManagedDocumentService.issue(db, document_id=draft.id, **issue)
    assert await db.scalar(count) == 1
    first = await db.scalar(select(CustomerContract).where(CustomerContract.source_document_id == draft.id))
    assert (first.customer_id, first.legal_entity_id, first.document_role_type, first.number) == (
        order.customer_id, issuer.id, "executor_customer", "Д-2026-001",
    )
    assert first.valid_from == datetime(2026, 4, 25)
    assert first.valid_until == datetime(2027, 4, 25)
    assert first.status == "active"
    replacement = await ManagedDocumentService.create_draft(db, **create, replaces_document_id=draft.id)
    with pytest.raises(ManagedDocumentGenerationError):
        await ManagedDocumentService.issue(db, document_id=replacement.id, **{**issue, "pdf_converter": FailingPdfConverter()})
    assert first.status == "active" and await db.scalar(count) == 1
    await ManagedDocumentService.issue(db, document_id=replacement.id, **issue)
    assert await db.scalar(count) == 2
    await db.refresh(first)
    assert first.status == "archived"
    second = await db.scalar(select(CustomerContract).where(CustomerContract.source_document_id == replacement.id))
    assert second.id != first.id and second.status == "active"
    await ManagedDocumentService.void(db, tenant_scope=scope, document_id=replacement.id, reason="Исправление")
    await db.refresh(second)
    assert second.status == "archived" and await db.scalar(count) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("ambiguous", [False, True])
async def test_pre_rollout_draft_registers_only_for_identifiable_frozen_customer(db, tmp_path, ambiguous):
    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path)
    customer = await db.get(Customer, order.customer_id)
    customer.inn = "310000234"
    await db.commit()
    draft = await ManagedDocumentService.create_draft(
        db, tenant_scope=scope, selection=_selection(order, issuer), template_storage=templates,
    )
    legacy_snapshot = deepcopy(draft.render_snapshot)
    legacy_snapshot["meta"].pop("customer_id")
    draft.render_snapshot = legacy_snapshot
    if ambiguous:
        db.add(Customer(tenant_id=scope.tenant_id, name="Другой контрагент", phone="987", inn=customer.inn))
    await db.commit()
    issue = dict(tenant_scope=scope, document_id=draft.id, template_storage=templates,
                 artifact_storage=artifacts, pdf_converter=FakePdfConverter())
    if ambiguous:
        with pytest.raises(ManagedDocumentConflictError, match="Сверьте клиента"):
            await ManagedDocumentService.issue(db, **issue)
        assert await db.scalar(select(func.count()).select_from(DocumentNumberReservation)) == 0
        assert await db.scalar(select(func.count()).select_from(CustomerContract)) == 0
    else:
        await ManagedDocumentService.issue(db, **issue)
        item = await db.scalar(select(CustomerContract))
        assert item.customer_id == customer.id == draft.render_snapshot["meta"]["customer_id"]


@pytest.mark.asyncio
async def test_racing_issue_calls_register_framework_once(db_engine, tmp_path):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions() as db:
        scope, order, issuer, templates, artifacts = await _seed(db, tmp_path)
        draft = await ManagedDocumentService.create_draft(
            db, tenant_scope=scope, selection=_selection(order, issuer), template_storage=templates,
        )
    barrier = Barrier(2, timeout=20)

    class WaitForOtherRender(FakePdfConverter):
        def convert_docx(self, content, *, filename="document.docx"):
            barrier.wait()
            return super().convert_docx(content, filename=filename)

    async def issue():
        async with sessions() as session:
            result = await ManagedDocumentService.issue(
                session, tenant_scope=scope, document_id=draft.id, template_storage=templates,
                artifact_storage=artifacts, pdf_converter=WaitForOtherRender(),
            )
            return result.document.official_number
    assert await asyncio.gather(issue(), issue()) == ["001", "001"]
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(CustomerContract)) == 1


@pytest.mark.asyncio
async def test_framework_source_and_cross_order_entry_share_basis_and_printed_sequence(db, tmp_path):
    from dataclasses import replace
    from models import Order
    from modules.documents.application import DocumentContextBuilder, DocumentContextError
    from modules.documents.domain import ActTerms
    from tests.integration.test_managed_document_lifecycle import _active_contract_template

    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path, document_type="act")
    await _active_contract_template(db, scope=scope, issuer=issuer, template_storage=templates,
                                    name="Рамочный договор", scenario="framework")
    create = dict(tenant_scope=scope, template_storage=templates)
    issue = dict(**create, artifact_storage=artifacts, pdf_converter=FakePdfConverter())
    framework = await ManagedDocumentService.create_draft(db, selection=_selection(order, issuer), **create)
    await ManagedDocumentService.issue(db, document_id=framework.id, **issue)
    entry = await db.scalar(select(CustomerContract).where(CustomerContract.source_document_id == framework.id))
    source = DocumentContextSelection(
        order_id=order.id, legal_entity_id=issuer.id, document_type="act", issue_date=date(2026, 5, 2),
        base_document_id=framework.id, act_terms=ActTerms(claims_status="none"),
    )
    automatic = await DocumentContextBuilder.build(db, tenant_scope=scope, selection=replace(source, base_document_id=None))
    assert automatic["meta"]["base_customer_contract_id"] == entry.id
    from services.document_service import DocumentService
    google_source, google_entry = await DocumentService._resolve_base_document(
        db, order_id=order.id, doc_type="act", base_document_id=framework.id, issue_date=source.issue_date,
    )
    assert google_source is None and google_entry.id == entry.id
    with pytest.raises(ValueError, match="на дату"):
        await DocumentService._resolve_base_document(
            db, order_id=order.id, doc_type="act", base_document_id=framework.id, issue_date=date(2028, 1, 1),
        )
    first = await ManagedDocumentService.create_draft(db, selection=source, **create)
    assert first.base_document_id is None and first.base_customer_contract_id == entry.id
    assert first.render_snapshot["values"]["basis.number"] == entry.number == "Д-2026-001"
    assert first.render_snapshot["meta"]["document_role_type"] == "executor_customer"
    # A saved draft crossing rollout can point to the source rather than the
    # equivalent register row, while its frozen print facts already match.
    first.base_document_id = framework.id
    first.base_customer_contract_id = None
    snap = deepcopy(first.render_snapshot)
    snap["meta"].update(base_customer_contract_id=None, base_document_id=framework.id)
    first.render_snapshot = snap
    await db.commit()
    await ManagedDocumentService.issue(db, document_id=first.id, **issue)
    assert first.base_document_id is None and first.base_customer_contract_id == entry.id
    assert first.contract_act_number == 1

    second_order = Order(tenant_id=scope.tenant_id, storefront_id=scope.storefront_id, customer_id=order.customer_id)
    db.add(second_order)
    await db.commit()
    with pytest.raises(DocumentContextError, match="в заказе"):
        await DocumentContextBuilder.build(db, tenant_scope=scope, selection=replace(source, order_id=second_order.id))
    second_choice = replace(source, order_id=second_order.id, base_document_id=None, base_customer_contract_id=entry.id)
    second = await ManagedDocumentService.create_draft(db, **create, selection=second_choice)
    await ManagedDocumentService.issue(db, document_id=second.id, **issue)
    assert second.contract_act_number == 2 and second.base_customer_contract_id == entry.id
    await ManagedDocumentService.void(db, document_id=framework.id, tenant_scope=scope, reason="Аннулирован")
    with pytest.raises(DocumentContextError, match="договор недоступен"):
        await DocumentContextBuilder.build(db, tenant_scope=scope, selection=second_choice)
    assert first.status == second.status == "issued"


@pytest.mark.asyncio
async def test_multiple_issuers_require_reviewed_open_contract_and_recheck_before_issue(db, tmp_path):
    from dataclasses import replace
    from models import DocumentLegalEntity
    from modules.documents.application import DocumentContextBuilder, DocumentContextError
    from modules.documents.domain import ActTerms

    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path, document_type="act")
    contract = CustomerContract(
        customer_id=order.customer_id, number="ОД-6", valid_from=datetime(2026, 1, 1),
        valid_until=datetime(2026, 12, 31), document_role_type="executor_customer",
    )
    db.add(contract)
    await db.commit()
    choice = DocumentContextSelection(
        order_id=order.id, legal_entity_id=issuer.id, document_type="act", issue_date=date(2026, 11, 5),
        base_customer_contract_id=contract.id, act_terms=ActTerms(claims_status="none"),
    )
    draft = await ManagedDocumentService.create_draft(db, tenant_scope=scope, selection=choice, template_storage=templates)
    other = DocumentLegalEntity(tenant_id=scope.tenant_id, slug="second-issuer", display_name="Другой исполнитель")
    db.add(other)
    await db.commit()
    with pytest.raises(DocumentContextError, match="юридическое лицо"):
        await DocumentContextBuilder.build(db, tenant_scope=scope, selection=choice)
    with pytest.raises(ManagedDocumentConflictError, match="юридическое лицо"):
        await ManagedDocumentService.issue(
            db, tenant_scope=scope, document_id=draft.id, template_storage=templates,
            artifact_storage=artifacts, pdf_converter=FakePdfConverter(),
        )
    contract.legal_entity_id = issuer.id
    await db.commit()
    snapshot = await DocumentContextBuilder.build(db, tenant_scope=scope, selection=choice)
    assert snapshot["meta"]["base_customer_contract_id"] == contract.id
    with pytest.raises(DocumentContextError, match="другому юридическому лицу"):
        await DocumentContextBuilder.build(db, tenant_scope=scope, selection=replace(choice, legal_entity_id=other.id))
    # The order also has a one-time native contract owned by the first issuer.
    other_choice = replace(choice, legal_entity_id=other.id, base_customer_contract_id=None)
    with pytest.raises(DocumentContextError, match="другому юридическому лицу"):
        await DocumentContextBuilder.build(
            db, tenant_scope=scope, selection=replace(other_choice, base_document_id=db.info["test_act_basis"].id),
        )
    with pytest.raises(DocumentContextError, match="нужен договор"):
        await DocumentContextBuilder.build(db, tenant_scope=scope, selection=other_choice)
    assert await db.scalar(select(func.count()).select_from(DocumentNumberReservation)) == 0


@pytest.mark.asyncio
async def test_framework_term_and_changed_order_customer_checked_before_number(db, tmp_path):
    from modules.documents.application import DocumentContextError
    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path)
    with pytest.raises(DocumentContextError, match="до даты выпуска"):
        await ManagedDocumentService.create_draft(
            db, tenant_scope=scope, template_storage=templates,
            selection=_selection(order, issuer, valid_until=date(2026, 4, 24)),
        )
    draft = await ManagedDocumentService.create_draft(
        db, tenant_scope=scope, template_storage=templates, selection=_selection(order, issuer),
    )
    new_customer = Customer(tenant_id=scope.tenant_id, name="Другой покупатель", phone="2", type="company")
    db.add(new_customer)
    await db.flush()
    order.customer_id = new_customer.id
    await db.commit()
    with pytest.raises(ManagedDocumentConflictError, match="Сверьте клиента"):
        await ManagedDocumentService.issue(
            db, tenant_scope=scope, document_id=draft.id, template_storage=templates,
            artifact_storage=artifacts, pdf_converter=FakePdfConverter(),
        )
    assert await db.scalar(select(func.count()).select_from(DocumentNumberReservation)) == 0


@pytest.mark.asyncio
async def test_registry_migration_preserves_legacy_and_protects_real_issuer_mapping(db_engine):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from models import DocumentLegalEntity

    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        customer = Customer(tenant_id=1, name="Контрагент с историей", phone="23")
        issuer = DocumentLegalEntity(tenant_id=1, display_name="Продавец", slug="migration-issuer")
        session.add_all([customer, issuer])
        await session.flush()
        old = CustomerContract(customer_id=customer.id, number="ОД-2026-002",
                               valid_until=datetime(2027, 4, 25), google_file_id="original")
        session.add(old)
        await session.flush()

    path = Path(__file__).resolve().parents[2] / "alembic/versions/doc20261105reg01_framework_contract_registry.py"
    spec = importlib.util.spec_from_file_location("framework_registry_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def check(connection):
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
        migration.upgrade()
        row = connection.execute(text(
            "SELECT google_file_id, legal_entity_id, source_document_id FROM customer_contract WHERE id=:id"
        ), {"id": old.id}).one()
        assert tuple(row) == ("original", None, None)
        connection.execute(text("UPDATE customer_contract SET legal_entity_id=:issuer WHERE id=:id"),
                           {"issuer": issuer.id, "id": old.id})
        with pytest.raises(RuntimeError, match="привязки"):
            migration.downgrade()

    async with db_engine.begin() as connection:
        await connection.run_sync(check)
