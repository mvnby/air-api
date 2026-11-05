from datetime import datetime

import pytest

from models import Customer, CustomerContract, DocumentLegalEntity, Order, OrderDocument, Storefront
from models.tenancy import TenantScope
from services.customer_contract_service import ContractHistoryConflict, CustomerContractService
from services.customer_reconciliation_legacy_review import LEGACY_META_KEY

SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.mark.asyncio
async def test_confirm_legacy_parties_preserves_original_and_reviewed_history(db, monkeypatch):
    def disallow_drive():
        pytest.fail("Updating the register must not rewrite the Google original")
    monkeypatch.setattr("services.customer_contract_service.get_google_service", disallow_drive)
    buyer = Customer(tenant_id=1, name="Тестовое предприятие", phone="")
    issuer = DocumentLegalEntity(tenant_id=1, slug="issuer", display_name="ИП Исполнитель")
    db.add_all([buyer, issuer])
    await db.flush()
    contract = CustomerContract(customer_id=buyer.id, number="ОД-2026-009",
                                valid_until=datetime(2027, 4, 25), google_file_id="original-file")
    db.add(contract)
    await db.commit()
    kwargs = dict(customer_id=buyer.id, contract_id=contract.id, tenant_scope=SCOPE)
    with pytest.raises(ValueError, match="исполнителя"):
        await CustomerContractService.update_for_customer(db, **kwargs, payload={
            "legal_entity_id": issuer.id + 100, "document_role_type": "executor_customer",
        })
    await CustomerContractService.update_for_customer(db, **kwargs, payload={
        "legal_entity_id": issuer.id, "document_role_type": "executor_customer",
    })
    items = (await CustomerContractService.list_for_customer(db, buyer.id, tenant_scope=SCOPE))["items"]
    assert items[0]["document_role_type"] == "executor_customer"
    assert items[0]["legal_entity_id"] == issuer.id and items[0]["can_delete"]
    order = Order(tenant_id=1, storefront_id=1, customer_id=buyer.id)
    db.add(order)
    await db.flush()
    db.add(OrderDocument(order_id=order.id, doc_type="act", number="А-2026-001",
                         scope_meta={LEGACY_META_KEY: {"contract_id": contract.id}}))
    await db.commit()
    with pytest.raises(ContractHistoryConflict):
        await CustomerContractService.delete_for_customer(db, **kwargs)
    items = (await CustomerContractService.list_for_customer(db, buyer.id, tenant_scope=SCOPE))["items"]
    assert not items[0]["can_delete"]
    assert contract.google_file_id == "original-file"


@pytest.mark.asyncio
async def test_native_source_link_is_storefront_scoped_and_does_not_advance_legacy_series(db):
    customer = Customer(tenant_id=1, name="Тестовый клиент", phone="")
    other_site = Storefront(tenant_id=1, slug="site-b", display_name="Филиал")
    issuer = DocumentLegalEntity(tenant_id=1, slug="issuer", display_name="Исполнитель")
    db.add_all([customer, other_site, issuer])
    await db.flush()
    order = Order(tenant_id=1, storefront_id=other_site.id, customer_id=customer.id)
    db.add(order)
    await db.flush()
    source = OrderDocument(order_id=order.id, tenant_id=1, legal_entity_id=issuer.id, doc_type="contract",
                           number="Д-2026-099", status="issued", internal_reference="test-source")
    db.add(source)
    await db.flush()
    for number, source_id in (("ОД-2026-015", None), ("ОД-2026-xxx", None), (source.number, source.id)):
        db.add(CustomerContract(customer_id=customer.id, number=number, source_document_id=source_id,
                                legal_entity_id=issuer.id if source_id else None,
                                valid_until=datetime(2027, 5, 20)))
    await db.commit()
    for site, permitted in ((1, False), (other_site.id, True)):
        rows = (await CustomerContractService.list_for_customer(
            db, customer.id, tenant_scope=TenantScope(tenant_id=1, storefront_id=site)
        ))["items"]
        item = next(row for row in rows if row["source_kind"] == "crm")
        assert item["source_document_id"] == (source.id if permitted else None)
        assert item["source_order_id"] == (order.id if permitted else None)
        assert not item["can_delete"]
    assert await CustomerContractService._get_next_number(db, datetime(2026, 6, 1)) == "ОД-2026-016"
