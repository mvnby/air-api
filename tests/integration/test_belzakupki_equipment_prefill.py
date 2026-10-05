from unittest.mock import AsyncMock
import json
from pathlib import Path

import pytest
from sqlmodel import select

from models import (
    Brand, Customer, LeadSource, Order, OrderProductLink, OrderProposal, OrderStatus, Product,
    Storefront, Tenant, TenantCatalogGrant, TenantOffer,
)
from models.supplier import ProductLocalStock, ProductSupplierMapping, Supplier, SupplierOffer
from models.tenancy import TenantScope
from models.common import CustomerType
from schemas_belzakupki_enrichment import ManagerOrderSourceApply, SourceEquipmentDraft, SourceObjectDraft
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.belzakupki_equipment_prefill import BelzakupkiEquipmentPrefillService


@pytest.mark.asyncio
async def test_review_fills_linked_customer_without_switching_to_another_unp_match(db, monkeypatch):
    detail = json.loads((Path(__file__).parents[1] / "fixtures/tender_customer/464.json").read_text())
    name = detail["customer"]["name"]
    old = Customer(tenant_id=1, name=name, type=CustomerType.company, inn="300050210", email="old-office@example.test")
    linked = Customer(tenant_id=1, name=name, full_legal_name=name, type=CustomerType.company, legal_address="Сохранённый адрес")
    db.add_all([old, linked])
    await db.flush()
    order = Order(tenant_id=1, storefront_id=1, customer_id=linked.id, status=OrderStatus.NEGOTIATION,
                  lead_source=LeadSource.BELZAKUPKI, workflow_type="maintenance",
                  technical_meta={"service_type": "maintenance", "belzakupki": {
                      "source": "goszakupki_by", "external_tender_id": "3722135",
                  }})
    db.add(order)
    await db.commit()
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value=detail))
    monkeypatch.setattr("services.belzakupki_customer_service.fetch_registry_data", AsyncMock(return_value={}))
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    preview = await BelzakupkiEnrichmentService.preview(db, order_id=order.id, scope=scope)
    assert preview.existing_customer_id == linked.id
    assert any(f"№{old.id}" in warning for warning in preview.warnings)
    result = await BelzakupkiEnrichmentService.apply(
        db, order_id=order.id, scope=scope, username="test",
        payload=ManagerOrderSourceApply(customer_action="existing", customer_id=linked.id,
                                       customer=preview.customer, objects=[], document_ids=[]),
    )
    await db.refresh(linked)
    await db.refresh(order)
    await db.refresh(old)
    assert result.customer_id == order.customer_id == linked.id
    assert linked.inn == "300050210" and linked.email == "marketing@vokb.vitebsk.by"
    assert linked.iban == "BY35BLBB36040300050210001001" and linked.bic == "BLBBBY2X"
    assert linked.legal_address == "Сохранённый адрес"
    assert old.email == "old-office@example.test"
    assert order.technical_meta["belzakupki"]["enrichment"]["submission"]["method"] == "email"


async def _products(db):
    brand = Brand(title="MDV", slug="prefill-mdv")
    supplier = Supplier(name="Prefill supplier", code="prefill-supplier")
    db.add_all([brand, supplier])
    await db.flush()
    products = []
    for size, price in (("12", 2990), ("09", 2690)):
        product = Product(
            title=f"MDV INFINI Nordic Heat Pump MDSAN-{size}HRFN8/MDOAN-{size}HFN8",
            slug=f"prefill-mdv-{size}", brand_id=brand.id, price=price, product_kind="complete_split_system",
            specs={"model_indoor": f"MDSAN-{size}HRFN8", "model_outdoor": f"MDOAN-{size}HFN8",
                   "wifi_state": "builtin", "wifi_builtin": True},
        )
        db.add(product)
        await db.flush()
        external_id = f"MODEL-{size}"
        db.add_all([
            SupplierOffer(supplier_id=supplier.id, external_id=external_id, qty=20,
                          wholesale_currency="BYN", wholesale_value=2100),
            ProductSupplierMapping(supplier_id=supplier.id, product_id=product.id, external_id=external_id),
        ])
        products.append(product)
    await db.flush()
    return products


def _objects():
    return [SourceObjectDraft(address="Объект", equipment=[
        SourceEquipmentDraft(brand="MDV", model="MDSAN-12HRFN8 (WF) / MDOAN-12HFN8", quantity=9),
        SourceEquipmentDraft(brand="MDV", model="MDSAN-09HRFN8 (WF) / MDOAN-09HFN8", quantity=5),
    ])]


@pytest.mark.asyncio
async def test_source_apply_persists_exact_mdv_pair_lines_financials_report_and_reapply(db, monkeypatch):
    products = await _products(db)
    order = Order(
        tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION, lead_source=LeadSource.BELZAKUPKI,
        workflow_type="maintenance",
        technical_meta={"service_type": "maintenance", "belzakupki": {"source": "goszakupki_by", "external_tender_id": "PREFILL-1",
            "enrichment": {"source": "goszakupki_by", "external_id": "PREFILL-1", "objects": [obj.model_dump() for obj in _objects()]}}},
    )
    db.add(order)
    await db.commit()
    order_id = int(order.id)
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value={
        "source": "goszakupki_by", "external_id": "PREFILL-1", "documents": [], "customer": {},
    }))
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    payload = ManagerOrderSourceApply(customer_action="skip", workflow_type="sales_installation", service_type="turnkey")
    assert "objects" not in payload.model_fields_set
    first = await BelzakupkiEnrichmentService.apply(db, order_id=order_id, scope=scope, payload=payload, username="test")
    assert [item.product_id for item in first.equipment_prefill.added] == [product.id for product in products]
    lines = list((await db.execute(select(OrderProductLink).where(OrderProductLink.order_id == order_id).order_by(OrderProductLink.id))).scalars().all())
    assert [(line.quantity, line.price, line.cost) for line in lines] == [(9, 2990, 2100), (5, 2690, 2100)]
    proposal = (await db.execute(select(OrderProposal).where(OrderProposal.order_id == order_id))).scalar_one()
    assert proposal.status == "draft" and proposal.is_selected
    assert all(line.proposal_id == proposal.id and not line.is_installation_included for line in lines)
    await db.refresh(order)
    assert order.total_amount == 9 * 2990 + 5 * 2690
    assert order.technical_meta["belzakupki"]["enrichment"]["equipment_prefill"]["added"][0]["quantity"] == 9
    lines[0].quantity = 2
    lines[0].price = 2400
    db.add(lines[0])
    await db.delete(lines[1])
    await db.commit()
    second = await BelzakupkiEnrichmentService.apply(db, order_id=order_id, scope=scope, payload=payload, username="test")
    assert not second.equipment_prefill.added
    assert [item.reason for item in second.equipment_prefill.skipped] == ["already_processed", "already_processed"]
    remaining = (await db.execute(select(OrderProductLink).where(OrderProductLink.order_id == order_id))).scalar_one()
    assert (remaining.quantity, remaining.price) == (2, 2400)
    preview = await BelzakupkiEnrichmentService.preview(db, order_id=order_id, scope=scope)
    assert preview.equipment_prefill.skipped[0].reason == "already_processed"
    assert preview.equipment_prefill.warnings


@pytest.mark.asyncio
async def test_candidate_query_enforces_storefront_grant_price_and_active_supply(db):
    products = await _products(db)
    tenant = Tenant(slug="prefill-tenant", display_name="Prefill tenant")
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug="main", display_name="Main", status="active")
    other_storefront = Storefront(tenant_id=tenant.id, slug="other", display_name="Other", status="active")
    db.add_all([storefront, other_storefront])
    await db.flush()
    grant = TenantCatalogGrant(tenant_id=tenant.id, storefront_id=storefront.id, status="active",
                               created_by_username="test", updated_by_username="test")
    db.add(grant)
    await db.flush()
    db.add_all([
        TenantOffer(tenant_id=tenant.id, storefront_id=storefront.id, product_id=products[0].id,
                    catalog_grant_id=grant.id, is_published=True, price=3990,
                    created_by_username="test", updated_by_username="test"),
        TenantOffer(tenant_id=tenant.id, storefront_id=other_storefront.id, product_id=products[1].id,
                    is_published=True, price=1, created_by_username="test", updated_by_username="test"),
    ])
    inactive = Supplier(name="Inactive", code="prefill-inactive", is_active=False)
    db.add(inactive)
    await db.flush()
    db.add_all([
        SupplierOffer(supplier_id=inactive.id, external_id="INACTIVE", qty=900, wholesale_value=1, wholesale_currency="BYN"),
        ProductSupplierMapping(supplier_id=inactive.id, external_id="INACTIVE", product_id=products[0].id),
        ProductLocalStock(product_id=products[0].id, qty=2),
    ])
    await db.commit()
    scope = TenantScope(tenant_id=int(tenant.id), storefront_id=int(storefront.id))
    candidates = await BelzakupkiEquipmentPrefillService.candidates(
        db, scope=scope, models={"mdsan-12hrfn8(wf)/mdoan-12hfn8", "mdsan-09hrfn8(wf)/mdoan-09hfn8"},
    )
    assert len(candidates) == 1
    assert (candidates[0].product.id, candidates[0].price, candidates[0].cost, candidates[0].available_quantity) == (products[0].id, 3990, 2100, 22)
    grant.status = "disabled"
    db.add(grant)
    await db.commit()
    assert not await BelzakupkiEquipmentPrefillService.candidates(db, scope=scope, models={"mdsan-12hrfn8/mdoan-12hfn8"})
