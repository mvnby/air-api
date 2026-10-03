from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from models import Customer, Order, OrderDocument, Payment
from models.common import CustomerType, OrderStatus
from models.tenancy import TenantScope
from schemas_manager_orders import ManagerCustomerReconciliationEventRelationPayload
from services.customer_reconciliation_event_relation import (
    ReconciliationEventRelationError, confirm_event_relation,
)
from services.customer_reconciliation_projection import project


def legacy_doc(doc_id: int, doc_type: str, order_id: int) -> OrderDocument:
    file_id = f"google-{doc_id}"
    return OrderDocument(
        id=doc_id, order_id=order_id, doc_type=doc_type,
        number=f"crm-{doc_id}", date=datetime(2026, 2, 2), google_file_id=file_id,
        scope_meta={"reconciliation_legacy_confirmation": {
            "source_file_id": file_id, "source_hash": "a" * 64,
            "number": str(doc_id), "date": "2026-02-02", "amount": 200,
            "contract_id": None, "evidence_excerpt": "Акт №1 от 02.02.2026",
        }},
    )


@pytest.mark.asyncio
async def test_explicit_event_relation_persists_and_expires_with_evidence():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: SQLModel.metadata.create_all(
            sync, tables=[Customer.__table__, Order.__table__, OrderDocument.__table__, Payment.__table__],
        ))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(Customer(id=1, tenant_id=1, name="Тест", phone="+375291111111",
                             type=CustomerType.company))
        session.add(Customer(id=2, tenant_id=2, name="Чужой", phone="+375292222222",
                             type=CustomerType.company))
        await session.flush()
        own = Order(id=1, tenant_id=1, storefront_id=1, customer_id=1,
                    status=OrderStatus.CLOSED, closing_result="won", total_amount=1000)
        foreign = Order(id=2, tenant_id=2, storefront_id=2, customer_id=2,
                        status=OrderStatus.CLOSED, closing_result="won", total_amount=1000)
        session.add_all([own, foreign])
        await session.flush()
        first = legacy_doc(1, "act", 1)
        second = legacy_doc(2, "tn2", 1)
        alien = legacy_doc(3, "act", 2)
        session.add_all([first, second, alien])
        await session.commit()
        await session.refresh(own, attribute_names=["documents", "payments"])
        start, end = datetime(2026, 1, 1), datetime(2026, 12, 31, 23, 59, 59)
        initial = project([own], start, end)
        assert initial["documents_total"] == 200
        assert initial["ready_for_generation"] is False
        assert initial["warnings"][0]["related_document_ids"] == [1, 2]

        scope = TenantScope(tenant_id=1, storefront_id=1)
        with pytest.raises(ReconciliationEventRelationError, match="одному заказу"):
            await confirm_event_relation(
                session, customer_id=1, tenant_scope=scope, confirmed_by="manager",
                payload=ManagerCustomerReconciliationEventRelationPayload(
                    document_ids=[1, 3], relation="same", reason="Один акт и накладная",
                ),
            )

        await confirm_event_relation(
            session, customer_id=1, tenant_scope=scope, confirmed_by="manager",
            payload=ManagerCustomerReconciliationEventRelationPayload(
                document_ids=[1, 2], relation="same", reason="Одна поставка по оригиналам",
            ),
        )
        same = project([own], start, end)
        assert same["documents_total"] == 200
        assert same["ready_for_generation"] is True
        stored = first.scope_meta["reconciliation_event_relations"]["1-2"]
        assert stored["confirmed_by"] == "manager"

        confirmation = dict(second.scope_meta["reconciliation_legacy_confirmation"])
        confirmation["amount"] = 250
        second.scope_meta = {**second.scope_meta, "reconciliation_legacy_confirmation": confirmation}
        stale = project([own], start, end)
        assert stale["ready_for_generation"] is False
        assert any(item["code"] == "event_relation_stale" for item in stale["warnings"])
    await engine.dispose()


@pytest.mark.asyncio
async def test_separate_relation_preserves_both_amounts():
    first = legacy_doc(1, "act", 1)
    second = legacy_doc(2, "tn2", 1)
    from services.customer_reconciliation_projection import EVENT_RELATIONS_META_KEY, event_fingerprint
    record = {
        "document_ids": [1, 2], "relation": "separate", "reason": "Две поставки",
        "confirmed_at": "2026-02-03T00:00:00+00:00",
        "fingerprints": {"1": event_fingerprint(first), "2": event_fingerprint(second)},
    }
    first.scope_meta = {**first.scope_meta, EVENT_RELATIONS_META_KEY: {"1-2": record}}
    second.scope_meta = {**second.scope_meta, EVENT_RELATIONS_META_KEY: {"1-2": record}}
    own = Order(id=1, tenant_id=1, storefront_id=1, customer_id=1,
                status=OrderStatus.CLOSED, closing_result="won", total_amount=1000)
    own.documents = [first, second]
    own.payments = []
    result = project([own], datetime(2026, 1, 1), datetime(2026, 12, 31, 23, 59, 59))
    assert result["documents_total"] == 400
    assert result["ready_for_generation"] is True
