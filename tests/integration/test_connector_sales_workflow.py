"""Repeated real OAuth -> MCP -> chosen turnkey order -> native offer journeys."""

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import func, select

from models import Brand, Customer, GlobalConfig, InstallationPriceBook, Order, OrderDocument, Product
from tests.integration.test_connector_sales_order import sales_db
from tests.integration.test_connector_mcp_maintenance import grant, client_for, call, success
from tests.integration.test_installation_estimate_confirmation import _entry
from tests.integration.test_managed_document_lifecycle import _seed


@pytest.mark.asyncio
@pytest.mark.parametrize("attempt", range(10))
async def test_sales_journey_repeats_without_duplicates_and_resumes(sales_db, tmp_path, monkeypatch, attempt):
    db = sales_db
    _, original, issuer, storage, _ = await _seed(db, tmp_path, document_type="offer")
    monkeypatch.setattr("services.connector_sales_order._storage", lambda: storage)
    base = (await db.execute(select(Product))).scalars().one()
    specs = {"area_m2": 25, "capacity_cooling_kw": 2.5, "indoor_type": "настенный",
             "pipe_liquid": '1/4"', "pipe_gas": '3/8"'}
    for index in range(3):
        brand = Brand(title=f"Sales brand {index}", slug=f"sales-brand-{index}")
        db.add(brand)
        await db.flush()
        product = base if index == 0 else Product(title=f"Alternative {index}", slug=f"sales-alternative-{index}")
        product.product_kind = "complete_split_system"
        product.specs = specs
        product.power_cooling = 2.5
        product.brand_id = brand.id
        product.price = 1500 + index * 200
        db.add(product)
    db.add(InstallationPriceBook(tenant_id=1, revision=1, fingerprint="sales-workflow-book", entries=[_entry()]))
    if attempt % 2:
        db.add(GlobalConfig(key="install_discount", value="100"))
    expected_installation = Decimal("480.75" if attempt % 2 else "580.75")
    await db.commit()
    token, _, membership, _ = await grant(db, scopes="kitlane:read kitlane:orders:write kitlane:catalog:write kitlane:customers:write")
    installation = {"route_length_m": "6", "holes_by_type": {"diamond": 2}, "access": "standard",
                    "assumptions": ["Предварительно: длина трассы 6 м, два отверстия"]}
    async with client_for(db, token) as client:
        selection = success(await call(client, "select_sales_installation_options", {
            "area_m2": 25, "budget_byn": "3000", "installation": installation,
        }))
        assert selection["status"] == "ready" and len(selection["options"]) == 3
        choice = selection["options"][attempt % 3]
        # Compare against the independent native tariff fixture, not just the
        # connector's own aggregate calculation.
        assert Decimal(choice["installation_total_byn"]) == expected_installation
        assert Decimal(choice["total_byn"]) == Decimal(choice["equipment_total_byn"]) + expected_installation
        customer_id = original.customer_id
        if attempt % 2:
            customer_args = {"customer": {"type": "individual", "name": "Покупатель из чата", "phone": "+375291234567"},
                             "idempotency_key": f"sales-workflow-customer-{attempt}"}
            created = success(await call(client, "create_sales_customer", customer_args))
            customer_id = created["result"]["customer_id"]
            assert success(await call(client, "create_sales_customer", customer_args))["replayed"]
        args = {"customer_id": customer_id, "product_id": choice["product"]["product_id"],
                "installation": installation, "expected_calculation_fingerprint": choice["calculation_fingerprint"],
                "request_text": "Одна комната 25 м², бюджет с монтажом 3000 BYN",
                "requirements_text": "Выбран один вариант, условия монтажа предварительные",
                "idempotency_key": f"sales-workflow-save-{attempt}"}
        saved = success(await call(client, "save_sales_order", args))["result"]
        assert saved["workflow_type"] == "sales_installation" and saved["service_type"] == "turnkey"
        assert Decimal(saved["total_byn"]) == Decimal(choice["total_byn"])
        replay = success(await call(client, "save_sales_order", args))
        assert replay["replayed"] and replay["result"]["order_id"] == saved["order_id"]

    # A fresh HTTP/MCP client has no previous conversation state.
    async with client_for(db, token) as client:
        resumed = success(await call(client, "get_sales_order", {"order_id": saved["order_id"]}))
        assert resumed["request_text"] == args["request_text"]
        assert resumed["requirements_text"] == args["requirements_text"]
        assert resumed["saved_selection"]["installation"]["assumptions"] == installation["assumptions"]
        offer_args = {"order_id": saved["order_id"], "proposal_id": saved["proposal_id"],
                      "expected_version": resumed["version"], "legal_entity_id": issuer.id,
                      "issue_date": date(2026, 11, 7).isoformat(), "idempotency_key": f"sales-workflow-offer-{attempt}"}
        offer = success(await call(client, "prepare_sales_order_offer", offer_args))["result"]
        assert offer["status"] == "draft" and not offer["stale"]
        assert Decimal(offer["total_byn"]) == Decimal(choice["total_byn"])
        assert success(await call(client, "prepare_sales_order_offer", offer_args))["replayed"]
        document = success(await call(client, "get_sales_order_offer", {"document_id": offer["document_id"]}))
        assert document["proposal_id"] == saved["proposal_id"]
        assert f"documentId={offer['document_id']}" in document["manager_url"]
        # The existing connection cannot retain access after its membership changes.
        membership.role = "manager"
        await db.commit()
        denied = await client.post("/api/connector/mcp", json={"jsonrpc": "2.0", "id": 9,
            "method": "tools/call", "params": {"name": "get_sales_order", "arguments": {"order_id": saved["order_id"]}}})
        assert denied.status_code == 401
    assert await db.scalar(select(func.count()).select_from(Order)) == 2
    assert await db.scalar(select(func.count()).select_from(OrderDocument)) == 1
    assert await db.scalar(select(func.count()).select_from(Customer)) == (2 if attempt % 2 else 1)
