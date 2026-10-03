from datetime import date, datetime
from io import BytesIO

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from models import BankReceipt, Customer, CustomerContract, Order, OrderDocument, Payment
from models.common import CustomerType, OrderStatus
from models.tenancy import TenantScope
from schemas_manager_orders import ManagerLegacyReconciliationConfirmPayload
from services import customer_reconciliation_legacy_review as review_service
from services.customer_reconciliation_projection import document_identity
from services.customer_reconciliation_service import CustomerReconciliationService


ORIGINAL = "Акт №1 от 02.02.2026\nК договору №C-7\nИтого 250,00 BYN\nПодписи сторон"
RUSSIAN_ORIGINAL = (
    "Акт №1\n«02» февраля 2026 г.\n"
    "К договору №C-7 от 15.01.2025\nИтого 250,00 BYN\nПодписи сторон"
)


@pytest.fixture
async def legacy_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: SQLModel.metadata.create_all(
            sync, tables=[Customer.__table__, CustomerContract.__table__,
                          Order.__table__, OrderDocument.__table__,
                          Payment.__table__, BankReceipt.__table__],
        ))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        customer = Customer(id=1, tenant_id=1, name="Тест", phone="+375291111111",
                            type=CustomerType.company)
        other = Customer(id=2, tenant_id=2, name="Другой", phone="+375292222222",
                         type=CustomerType.company)
        session.add_all([customer, other])
        await session.flush()
        session.add(CustomerContract(id=7, customer_id=1, number="C-7",
                                     valid_from=datetime(2026, 1, 1),
                                     valid_until=datetime(2027, 1, 1)))
        session.add_all([
            Order(id=1, tenant_id=1, storefront_id=1, customer_id=1,
                  status=OrderStatus.CLOSED, closing_result="won", title="Заказ", total_amount=1000),
            Order(id=2, tenant_id=2, storefront_id=2, customer_id=2,
                  status=OrderStatus.CLOSED, closing_result="won", title="Чужой", total_amount=1000),
        ])
        await session.flush()
        session.add_all([
            OrderDocument(id=1, order_id=1, doc_type="act", number="135",
                          date=datetime(2026, 3, 1), google_file_id="google-one"),
            OrderDocument(id=2, order_id=2, doc_type="act", number="2",
                          date=datetime(2026, 3, 1), google_file_id="google-two"),
        ])
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_review_reads_original_and_confirms_only_scoped_document(legacy_session, monkeypatch):
    text = {"value": ORIGINAL}

    class Google:
        def export_file(self, file_id, mime_type):
            assert file_id == "google-one"
            return BytesIO(text["value"].encode())

    monkeypatch.setattr(review_service, "get_google_service", lambda: Google())
    scope = TenantScope(tenant_id=1, storefront_id=1)
    assert await review_service.review_legacy_document(legacy_session, 1, 2, scope) is None
    assert await review_service.review_legacy_document(
        legacy_session, 1, 1, TenantScope(tenant_id=1, storefront_id=2)
    ) is None

    review = await review_service.review_legacy_document(legacy_session, 1, 1, scope)
    assert review["extracted_text"] == ORIGINAL
    assert review["proposed_number"] == "1"
    assert review["proposed_date"] == "2026-02-02"
    assert review["proposed_amount"] == 250
    assert review["proposed_contract_id"] == 7

    payload = ManagerLegacyReconciliationConfirmPayload(
        source_hash=review["source_hash"], number="1", date=date(2026, 2, 2),
        amount=250, contract_id=7, evidence_excerpt="Акт №1 от 02.02.2026",
    )
    result = await review_service.confirm_legacy_document(legacy_session, 1, 1, scope, payload, confirmed_by="manager")
    assert result["number"] == "1"
    saved = await legacy_session.get(OrderDocument, 1)
    assert saved.number == "135"  # CRM reference is not rewritten.
    assert saved.official_number is None
    assert saved.scope_meta[review_service.LEGACY_META_KEY]["source_hash"] == review["source_hash"]
    assert saved.scope_meta[review_service.LEGACY_META_KEY]["confirmed_by"] == "manager"
    assert document_identity(saved)["identity_source"] == "confirmed_legacy"
    assert document_identity(saved)["amount"] == 250

    text["value"] = ORIGINAL.replace("250,00", "350,00")
    with pytest.raises(review_service.LegacyDocumentReviewError, match="изменился"):
        await review_service.confirm_legacy_document(legacy_session, 1, 1, scope, payload, confirmed_by="manager")
    checked = await CustomerReconciliationService.build(
        legacy_session, 1, date(2026, 1, 1), date(2026, 12, 31),
        tenant_scope=scope, verify_sources=True,
    )
    assert checked["ready_for_generation"] is False
    assert any(item["code"] == "legacy_source_changed" for item in checked["warnings"])
    with pytest.raises(ValueError, match="неподтверждённые"):
        await CustomerReconciliationService.generate_google_doc(
            legacy_session, 1, date(2026, 1, 1), date(2026, 12, 31),
            tenant_scope=scope,
        )
    saved.google_file_id = "another-original"
    assert document_identity(saved)["identity_source"] == "unverified_legacy"


@pytest.mark.asyncio
async def test_confirm_rejects_foreign_contract_and_missing_evidence(legacy_session, monkeypatch):
    class Google:
        def export_file(self, file_id, mime_type):
            return BytesIO(ORIGINAL.encode())

    monkeypatch.setattr(review_service, "get_google_service", lambda: Google())
    scope = TenantScope(tenant_id=1, storefront_id=1)
    review = await review_service.review_legacy_document(legacy_session, 1, 1, scope)
    bad_excerpt = ManagerLegacyReconciliationConfirmPayload(
        source_hash=review["source_hash"], number="1", date=date(2026, 2, 2),
        amount=250, evidence_excerpt="Отсутствующий фрагмент",
    )
    with pytest.raises(review_service.LegacyDocumentReviewError, match="не найден"):
        await review_service.confirm_legacy_document(legacy_session, 1, 1, scope, bad_excerpt, confirmed_by="manager")
    foreign_contract = bad_excerpt.model_copy(update={
        "evidence_excerpt": "Акт №1 от 02.02.2026", "contract_id": 999,
    })
    with pytest.raises(review_service.LegacyDocumentReviewError, match="не принадлежит"):
        await review_service.confirm_legacy_document(legacy_session, 1, 1, scope, foreign_contract, confirmed_by="manager")
    wrong_identity = bad_excerpt.model_copy(update={
        "evidence_excerpt": "Акт №1 от 02.02.2026", "number": "135",
    })
    with pytest.raises(review_service.LegacyDocumentReviewError, match="номер"):
        await review_service.confirm_legacy_document(legacy_session, 1, 1, scope, wrong_identity, confirmed_by="manager")
    wrong_amount = bad_excerpt.model_copy(update={
        "evidence_excerpt": "Акт №1 от 02.02.2026", "amount": 1000,
    })
    with pytest.raises(review_service.LegacyDocumentReviewError, match="сумма"):
        await review_service.confirm_legacy_document(legacy_session, 1, 1, scope, wrong_amount, confirmed_by="manager")


@pytest.mark.asyncio
async def test_russian_act_date_is_proposed_and_contract_date_cannot_be_confirmed(legacy_session, monkeypatch):
    class Google:
        def export_file(self, file_id, mime_type):
            return BytesIO(RUSSIAN_ORIGINAL.encode())

    monkeypatch.setattr(review_service, "get_google_service", lambda: Google())
    scope = TenantScope(tenant_id=1, storefront_id=1)
    review = await review_service.review_legacy_document(legacy_session, 1, 1, scope)
    assert review["proposed_number"] == "1"
    assert review["proposed_date"] == "2026-02-02"
    assert review["proposed_contract_id"] == 7

    wrong_date = ManagerLegacyReconciliationConfirmPayload(
        source_hash=review["source_hash"], number="1", date=date(2025, 1, 15),
        amount=250, contract_id=7,
        evidence_excerpt="Акт №1 «02» февраля 2026 г. К договору №C-7 от 15.01.2025",
    )
    with pytest.raises(review_service.LegacyDocumentReviewError, match="дату самого документа"):
        await review_service.confirm_legacy_document(
            legacy_session, 1, 1, scope, wrong_date, confirmed_by="manager",
        )
    wrong_number = wrong_date.model_copy(update={
        "number": "C-7", "date": date(2026, 2, 2),
    })
    with pytest.raises(review_service.LegacyDocumentReviewError, match="номер"):
        await review_service.confirm_legacy_document(
            legacy_session, 1, 1, scope, wrong_number, confirmed_by="manager",
        )
    accepted = wrong_date.model_copy(update={
        "date": date(2026, 2, 2),
        "evidence_excerpt": "Акт №1 «02» февраля 2026 г.",
    })
    result = await review_service.confirm_legacy_document(
        legacy_session, 1, 1, scope, accepted, confirmed_by="manager",
    )
    assert result["date"] == date(2026, 2, 2)


@pytest.mark.asyncio
async def test_uncommon_number_format_can_be_confirmed_from_manual_heading_excerpt(legacy_session, monkeypatch):
    source = "Акт выполненных работ 1 от «02» февраля 2026 года\nИтого 250,00 BYN"

    class Google:
        def export_file(self, file_id, mime_type):
            return BytesIO(source.encode())

    monkeypatch.setattr(review_service, "get_google_service", lambda: Google())
    scope = TenantScope(tenant_id=1, storefront_id=1)
    review = await review_service.review_legacy_document(legacy_session, 1, 1, scope)
    assert review["proposed_number"] is None
    accepted = ManagerLegacyReconciliationConfirmPayload(
        source_hash=review["source_hash"], number="1", date=date(2026, 2, 2),
        amount=250, evidence_excerpt="Акт выполненных работ 1 от «02» февраля 2026 года",
    )
    result = await review_service.confirm_legacy_document(
        legacy_session, 1, 1, scope, accepted, confirmed_by="manager",
    )
    assert result["number"] == "1"
    false_number = accepted.model_copy(update={"number": "250", "evidence_excerpt": source})
    with pytest.raises(review_service.LegacyDocumentReviewError, match="номер и дату"):
        await review_service.confirm_legacy_document(
            legacy_session, 1, 1, scope, false_number, confirmed_by="manager",
        )
