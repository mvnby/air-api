from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from models import Brand, LeadSource, Order, OrderProductLink, OrderProposal, OrderStatus, Product, ProductTagLink, Tag, Tenant, TenantCatalogGrant, TenantOffer
from models.supplier import ProductLocalStock, ProductSupplierMapping, Supplier, SupplierOffer
from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import ManagerOrderSourceApply, SourceEquipmentDraft, SourceObjectDraft
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.belzakupki_equipment_prefill import (
    BelzakupkiEquipmentPrefillService, ExactCatalogCandidate, full_model_matches, normalize_model,
)


@pytest.mark.parametrize("model", [" aB–12 / cd_12 ", "AB-12/CD_12", "AB-12/\nCD_12"])
def test_only_case_whitespace_and_dash_are_normalized(model):
    assert normalize_model(model) == "ab-12/cd_12"
    assert normalize_model("AB12/CD_12") != normalize_model(model)


@pytest.mark.parametrize("title,model,expected", [
    ("Кондиционер MDV AB-12/CD-12", "AB-12/CD-12", True),
    ("Кондиционер MDV AB–12 / CD–12", "AB-12/CD-12", True),
    ("Кондиционер MDV AB-12 (WF) / CD-12", "AB-12(WF)/CD-12", True),
    ("Кондиционер MDV AB-12/CD-12", "AB-12", False),
    ("Кондиционер MDV AB-12 (WF)/CD-12", "AB-12", False),
    ("Кондиционер MDV AB-12-X", "AB-12", False),
    ("Кондиционер MDV XAB-12", "AB-12", False),
    ("Кондиционер MDV AB-12", "AB-1", False),
])
def test_legacy_title_requires_complete_model(title, model, expected):
    product = Product(title=title, slug="model", price=1000)
    assert full_model_matches(product, normalize_model(model)) is expected


@pytest.mark.parametrize("size", ["09", "12"])
def test_actual_mdv_pair_accepts_wf_only_with_verified_builtin_wifi(size):
    product = Product(
        title=f"MDV INFINI Nordic Heat Pump MDSAN-{size}HRFN8/MDOAN-{size}HFN8",
        slug="mdv", price=2990,
        specs={"model_indoor": f"MDSAN-{size}HRFN8", "model_outdoor": f"MDOAN-{size}HFN8",
               "wifi_state": "builtin", "wifi_builtin": True},
    )
    model = normalize_model(f"MDSAN-{size}HRFN8 (WF) / MDOAN-{size}HFN8")
    assert full_model_matches(product, model)
    assert not full_model_matches(product, normalize_model(f"MDSAN-{size}HRFN8"))
    assert not full_model_matches(product, model.replace("(wf)", "(other)"))
    product.specs["wifi_builtin"] = False
    assert not full_model_matches(product, model)
    product.specs["wifi_builtin"] = True
    product.specs["wifi_state"] = "ready"
    assert not full_model_matches(product, model)


def _objects(quantity=2, model="AB-12/CD-12", brand="MDV"):
    return [SourceObjectDraft(address="Объект", equipment=[SourceEquipmentDraft(
        brand=brand, model=model, quantity=quantity,
    )])]


def _candidate(product_id=5, quantity=8, price=2990, cost=2100):
    return ExactCatalogCandidate(
        product=Product(id=product_id, title="MDV AB-12/CD-12", slug=f"mdv-{product_id}", price=9999),
        brand="MDV", available_quantity=quantity, price=price, cost=cost,
    )


def _session(lines):
    result = MagicMock()
    result.scalars.return_value.all.return_value = lines
    session = AsyncMock()
    session.execute.return_value = result
    added = []
    def add(item):
        if isinstance(item, OrderProductLink):
            item.id = 50 + len(added)
            added.append(item)
    session.add = MagicMock(side_effect=add)
    return session, added


async def _apply(monkeypatch, *, candidates=None, lines=None, status="draft", objects=None, order=None):
    order = order or Order(id=3, tenant_id=1, storefront_id=1)
    session, added = _session(lines or [])
    monkeypatch.setattr(BelzakupkiEquipmentPrefillService, "candidates", AsyncMock(return_value=candidates if candidates is not None else [_candidate()]))
    monkeypatch.setattr("services.belzakupki_equipment_prefill.OrderService.ensure_default_proposal", AsyncMock(return_value=OrderProposal(id=9, order_id=3, is_selected=True, status=status)))
    monkeypatch.setattr("services.belzakupki_equipment_prefill.OrderService._refresh_order_financials", AsyncMock())
    result = await BelzakupkiEquipmentPrefillService.apply(
        session, order=order, scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        source="goszakupki_by", external_id="T-1", objects=objects or _objects(),
    )
    session.commit.assert_not_awaited()
    return result, added, order


@pytest.mark.asyncio
async def test_add_aggregates_objects_and_preserves_manager_lines_and_repeat_edits(monkeypatch):
    manager = OrderProductLink(id=20, order_id=3, proposal_id=9, product_id=88, price=444, quantity=7)
    objects = _objects(2) + _objects(3, brand="mdv")
    result, lines, order = await _apply(monkeypatch, lines=[manager], objects=objects)
    assert len(lines) == 1
    assert (lines[0].product_id, lines[0].quantity, lines[0].price, lines[0].cost) == (5, 5, 2990, 2100)
    assert (manager.quantity, manager.price) == (7, 444)
    assert result.added[0].quantity == 5
    assert len(order.technical_meta["belzakupki"]["equipment_prefill_history"]) == 1
    lines[0].quantity = 11
    lines[0].price = 1200
    repeated, added, _ = await _apply(monkeypatch, lines=lines, objects=_objects(12), order=order)
    assert not added
    assert repeated.skipped[0].reason == "already_processed"
    assert (lines[0].quantity, lines[0].price) == (11, 1200)
    # Removing a previously transferred line is also a manager decision.
    removed, added, _ = await _apply(monkeypatch, order=order)
    assert not added
    assert removed.skipped[0].reason == "already_processed"


@pytest.mark.asyncio
@pytest.mark.parametrize("candidates,reason", [
    ([], "not_found"), ([_candidate(), _candidate(6)], "ambiguous"),
    ([_candidate(quantity=1)], "insufficient_stock"), ([_candidate(price=0)], "missing_price"),
])
async def test_unavailable_ambiguous_or_unpriced_never_add(monkeypatch, candidates, reason):
    result, lines, _ = await _apply(monkeypatch, candidates=candidates)
    assert not lines
    assert result.skipped[0].reason == reason
    assert result.warnings


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["sent", "approved", "ready"])
async def test_never_edit_non_draft_proposal(monkeypatch, status):
    result, lines, _ = await _apply(monkeypatch, status=status)
    assert not lines
    assert result.skipped[0].reason == "proposal_not_draft"


@pytest.mark.asyncio
async def test_existing_manager_product_keeps_quantity_and_price(monkeypatch):
    line = OrderProductLink(id=7, order_id=3, proposal_id=9, product_id=5, quantity=1, price=1234)
    result, added, _ = await _apply(monkeypatch, lines=[line])
    assert not added
    assert (line.quantity, line.price) == (1, 1234)
    assert result.skipped[0].reason == "existing_line"


@pytest.mark.asyncio
async def test_unknown_cost_does_not_invent_wholesale_or_block_current_retail(monkeypatch):
    result, lines, _ = await _apply(monkeypatch, candidates=[_candidate(cost=None)])
    assert (lines[0].price, lines[0].cost) == (2990, 0)
    assert result.added
    assert "закупочная стоимость неизвестна" in result.warnings[0]


@pytest.mark.asyncio
async def test_aggregated_quantity_over_database_range_stays_pending(monkeypatch):
    result, lines, _ = await _apply(monkeypatch, candidates=[_candidate(quantity=5_000_000_000)],
                                    objects=_objects(2_000_000_000) + _objects(2_000_000_000))
    assert not lines
    assert result.skipped[0].quantity == 4_000_000_000
    assert result.skipped[0].reason == "invalid_quantity"


@pytest.mark.asyncio
async def test_missing_quantity_and_wrong_brand_remain_visible(monkeypatch):
    objects = [SourceObjectDraft(address="Адрес", equipment=[
        SourceEquipmentDraft(model="AB-12/CD-12"),
        SourceEquipmentDraft(brand="Other", model="AB-12/CD-12", quantity=1),
    ])]
    result, lines, _ = await _apply(monkeypatch, objects=objects)
    assert not lines
    assert [item.reason for item in result.skipped] == ["incomplete", "not_found"]


@pytest.mark.asyncio
async def test_actual_source_apply_reuses_reviewed_equipment_when_objects_are_omitted(monkeypatch):
    order = Order(id=3, tenant_id=1, storefront_id=1, lead_source=LeadSource.BELZAKUPKI,
                  status=OrderStatus.NEGOTIATION, workflow_type="maintenance", technical_meta={
        "service_type": "maintenance", "belzakupki": {"source": "goszakupki_by", "external_tender_id": "T-1",
            "enrichment": {"source": "goszakupki_by", "external_id": "T-1", "objects": [obj.model_dump() for obj in _objects(5)]}},
    })
    session, lines = _session([])
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value={"source": "goszakupki_by", "external_id": "T-1", "documents": []}))
    monkeypatch.setattr(BelzakupkiEquipmentPrefillService, "candidates", AsyncMock(return_value=[_candidate()]))
    monkeypatch.setattr("services.belzakupki_equipment_prefill.OrderService.ensure_default_proposal", AsyncMock(return_value=OrderProposal(id=9, order_id=3, is_selected=True, status="draft")))
    monkeypatch.setattr("services.belzakupki_equipment_prefill.OrderService._refresh_order_financials", AsyncMock())
    payload = ManagerOrderSourceApply(customer_action="skip", workflow_type="sales_installation", service_type="turnkey")
    assert "objects" not in payload.model_fields_set
    first = await BelzakupkiEnrichmentService.apply(session, order_id=3, scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True), payload=payload, username="manager")
    assert [(line.product_id, line.quantity) for line in lines] == [(5, 5)]
    assert first.equipment_prefill.added[0].quantity == 5
    assert order.technical_meta["belzakupki"]["enrichment"]["equipment_prefill"]["added"]
    assert order.technical_meta["belzakupki"]["equipment_prefill_history"]
    second = await BelzakupkiEnrichmentService.apply(session, order_id=3, scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True), payload=payload, username="manager")
    assert len(lines) == 1
    assert second.equipment_prefill.skipped[0].reason == "already_processed"


@pytest.mark.asyncio
@pytest.mark.parametrize("objects", [None, []])
async def test_explicit_empty_or_null_objects_never_replay_saved_equipment(monkeypatch, objects):
    order = Order(id=3, tenant_id=1, storefront_id=1, lead_source=LeadSource.BELZAKUPKI,
                  status=OrderStatus.NEGOTIATION, technical_meta={
        "belzakupki": {"source": "goszakupki_by", "external_tender_id": "T-1",
                       "enrichment": {"source": "goszakupki_by", "external_id": "T-1", "objects": [obj.model_dump() for obj in _objects()]}},
    })
    session, lines = _session([])
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value={"documents": []}))
    prefill = AsyncMock()
    monkeypatch.setattr(BelzakupkiEquipmentPrefillService, "apply", prefill)
    await BelzakupkiEnrichmentService.apply(session, order_id=3, scope=TenantScope(tenant_id=1, storefront_id=1),
                                          payload=ManagerOrderSourceApply(customer_action="skip", objects=objects), username="manager")
    prefill.assert_not_awaited()
    assert not lines


@pytest.mark.asyncio
async def test_real_candidate_query_uses_granted_storefront_price_and_only_active_supply(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [model.__table__ for model in (
        Brand, Product, ProductTagLink, Tag, Tenant, TenantCatalogGrant, TenantOffer,
        ProductLocalStock, ProductSupplierMapping, Supplier, SupplierOffer,
    )]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: SQLModel.metadata.create_all(sync, tables=tables))
        async with AsyncSession(engine, expire_on_commit=False) as session:
            monkeypatch.setattr("services.belzakupki_equipment_prefill.FxRateService.get_supplier_usd_byn_rate", AsyncMock(return_value=Decimal("3")))
            session.add_all([
                Tenant(id=2, slug="prefill", display_name="Prefill"),
                Brand(id=1, slug="mdv", title="MDV"),
                Supplier(id=1, code="active", name="Active"),
                Supplier(id=2, code="inactive", name="Inactive", is_active=False),
            ])
            await session.flush()
            product = Product(id=10, title="MDV MDSAN-12HRFN8/MDOAN-12HFN8", slug="mdv-12", price=9999,
                              product_kind="complete_split_system", brand_id=1,
                              specs={"model_indoor": "MDSAN-12HRFN8", "model_outdoor": "MDOAN-12HFN8", "wifi_state": "builtin", "wifi_builtin": True})
            hidden = Product(id=11, title=product.title, slug="hidden-12", price=1, specs=product.specs,
                             brand_id=1, product_kind="complete_split_system")
            indoor = Product(id=12, title=product.title, slug="component-12", price=1, specs=product.specs,
                             brand_id=1, product_kind="indoor_unit")
            session.add_all([product, hidden, indoor,
                TenantCatalogGrant(id=1, tenant_id=2, storefront_id=20, status="active", created_by_username="test", updated_by_username="test"),
                SupplierOffer(supplier_id=1, external_id="ACTIVE", qty=3, wholesale_value=2000, wholesale_currency="BYN"),
                SupplierOffer(supplier_id=2, external_id="INACTIVE", qty=999, wholesale_value=1, wholesale_currency="BYN"),
                ProductSupplierMapping(product_id=10, supplier_id=1, external_id="ACTIVE"),
                ProductSupplierMapping(product_id=10, supplier_id=2, external_id="INACTIVE"),
                ProductLocalStock(product_id=10, qty=2),
            ])
            await session.flush()
            for product_id, storefront in ((10, 20), (11, 21), (12, 20)):
                session.add(TenantOffer(tenant_id=2, storefront_id=storefront, catalog_grant_id=1, product_id=product_id,
                                       price=3333, is_published=True, created_by_username="test", updated_by_username="test"))
            await session.commit()
            scope = TenantScope(tenant_id=2, storefront_id=20)
            model = normalize_model("MDSAN-12HRFN8 (WF) / MDOAN-12HFN8")
            candidates = await BelzakupkiEquipmentPrefillService.candidates(session, scope=scope, models={model})
            assert len(candidates) == 1
            assert full_model_matches(candidates[0].product, model)
            assert (candidates[0].product.id, candidates[0].price, candidates[0].cost, candidates[0].available_quantity) == (10, 3333, 2000, 5)
            grant = await session.get(TenantCatalogGrant, 1)
            grant.status = "disabled"
            await session.commit()
            assert not await BelzakupkiEquipmentPrefillService.candidates(session, scope=scope, models={model})
    finally:
        await engine.dispose()
