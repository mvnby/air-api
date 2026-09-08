from __future__ import annotations

from datetime import date

import pytest

from core.config import settings
from models import (
    Brand,
    Customer,
    DocumentLegalEntity,
    Order,
    OrderProductLink,
    OrderProposal,
    OrderStatus,
    Product,
    ProductSeries,
    Storefront,
    Tenant,
    WarrantyPolicy,
)
from models.tenancy import TenantScope
from modules.documents.application.context_builder import (
    DocumentContextBuilder,
    DocumentContextSelection,
)


async def _auth_headers(async_client) -> dict[str, str]:
    response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _seed_defaults_order(db):
    brand = Brand(title="Midea", slug="midea-consumer-defaults-api")
    db.add(brand)
    await db.flush()
    series = ProductSeries(
        brand_id=brand.id,
        title="Breezeless",
        slug="breezeless-consumer-defaults-api",
    )
    selected_product = Product(
        title="Midea Canonical Model",
        slug="midea-canonical-consumer-defaults-api",
        price=1_000,
        brand_id=brand.id,
        series_id=series.id,
        specs={"warranty_months": 24},
    )
    alternative_product = Product(
        title="Alternative Model",
        slug="alternative-consumer-defaults-api",
        price=1_000,
    )
    customer = Customer(tenant_id=1, name="Покупатель", phone="+375291234567")
    issuer = DocumentLegalEntity(
        tenant_id=1,
        slug="consumer-defaults-issuer",
        display_name="ООО MVN",
        is_default=True,
        requisites={
            "offer_url": "https://mvn.by/offer",
            "offer_version": "1.0",
            "offer_published_on": "01.09.2026",
        },
    )
    db.add_all([series, selected_product, alternative_product, customer, issuer])
    await db.flush()
    order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        title="Owned consumer order",
    )
    other_storefront = Storefront(
        tenant_id=1,
        slug="consumer-defaults-other-storefront",
        display_name="Other storefront",
        status="active",
        is_default=False,
    )
    foreign_tenant = Tenant(
        slug="consumer-defaults-foreign-tenant",
        display_name="Foreign tenant",
        kind="independent_seller",
        status="active",
        is_system=False,
    )
    db.add_all([order, other_storefront, foreign_tenant])
    await db.flush()
    foreign_tenant_storefront = Storefront(
        tenant_id=foreign_tenant.id,
        slug="consumer-defaults-foreign-tenant-storefront",
        display_name="Foreign tenant storefront",
        status="active",
        is_default=True,
    )
    foreign_order = Order(
        tenant_id=1,
        storefront_id=other_storefront.id,
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        title="Foreign storefront order",
    )
    selected = OrderProposal(order_id=order.id, name="Selected", is_selected=True)
    alternative = OrderProposal(order_id=order.id, name="Alternative", sort_order=1)
    db.add_all([foreign_tenant_storefront, foreign_order, selected, alternative])
    await db.flush()
    foreign_tenant_order = Order(
        tenant_id=foreign_tenant.id,
        storefront_id=foreign_tenant_storefront.id,
        status=OrderStatus.NEGOTIATION,
        title="Foreign tenant order",
    )
    db.add(foreign_tenant_order)
    await db.flush()
    db.add_all(
        [
            OrderProductLink(
                order_id=order.id,
                proposal_id=selected.id,
                product_id=selected_product.id,
                quantity=1,
                price=1_000,
                title_snapshot="Old sold title must not override canonical model",
            ),
            OrderProductLink(
                order_id=order.id,
                proposal_id=alternative.id,
                product_id=alternative_product.id,
                quantity=1,
                price=1_000,
            ),
            OrderProductLink(
                order_id=foreign_order.id,
                product_id=selected_product.id,
                quantity=1,
                price=1_000,
            ),
            OrderProductLink(
                order_id=foreign_tenant_order.id,
                product_id=selected_product.id,
                quantity=1,
                price=1_000,
            ),
            WarrantyPolicy(name="Brand", brand_id=brand.id, duration_months=36),
            WarrantyPolicy(name="Series", series_id=series.id, duration_months=48),
            WarrantyPolicy(
                name="Product",
                product_id=selected_product.id,
                duration_months=60,
                terms="Условия продукта",
            ),
        ]
    )
    await db.commit()
    return (
        order,
        foreign_order,
        foreign_tenant_order,
        selected,
        alternative,
        issuer,
        selected_product,
    )


@pytest.mark.asyncio
async def test_consumer_defaults_api_scopes_order_and_proposal(async_client, db):
    (
        order,
        foreign_order,
        foreign_tenant_order,
        selected,
        alternative,
        _issuer,
        _product,
    ) = await _seed_defaults_order(db)
    headers = await _auth_headers(async_client)

    selected_response = await async_client.get(
        f"/api/manager/document-system/orders/{order.id}/consumer-defaults",
        params={"proposal_id": selected.id, "issue_date": "2026-09-09"},
        headers=headers,
    )
    alternative_response = await async_client.get(
        f"/api/manager/document-system/orders/{order.id}/consumer-defaults",
        params={"proposal_id": alternative.id, "issue_date": "2026-09-09"},
        headers=headers,
    )
    foreign_response = await async_client.get(
        f"/api/manager/document-system/orders/{foreign_order.id}/consumer-defaults",
        headers=headers,
    )
    foreign_tenant_response = await async_client.get(
        f"/api/manager/document-system/orders/{foreign_tenant_order.id}/consumer-defaults",
        headers=headers,
    )

    assert selected_response.status_code == 200, selected_response.text
    assert selected_response.json() == {
        "equipment_brand": "Midea",
        "equipment_model": "Midea Canonical Model",
        "equipment_serial": None,
        "goods_warranty_months": 60,
        "goods_warranty_terms": "Условия продукта",
    }
    assert alternative_response.status_code == 200, alternative_response.text
    assert alternative_response.json()["equipment_model"] == "Alternative Model"
    assert alternative_response.json()["goods_warranty_months"] == 36
    assert foreign_response.status_code == 404
    assert foreign_tenant_response.status_code == 404


@pytest.mark.asyncio
async def test_b2c_snapshot_freezes_automatic_consumer_defaults(db):
    (
        order,
        _foreign_storefront,
        _foreign_tenant,
        selected,
        _alternative,
        issuer,
        product,
    ) = await _seed_defaults_order(db)
    snapshot = await DocumentContextBuilder.build(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        selection=DocumentContextSelection(
            order_id=order.id,
            legal_entity_id=issuer.id,
            proposal_id=selected.id,
            document_type="b2c_supply_installation_act",
            issue_date=date(2026, 9, 9),
        ),
    )
    product.title = "Changed catalog model"
    db.add(product)
    await db.commit()

    assert snapshot["values"]["equipment.brand"] == "Midea"
    assert snapshot["values"]["equipment.model"] == "Midea Canonical Model"
    assert snapshot["values"]["equipment.serial"] == ""
    assert snapshot["values"]["warranty.goods.months"] == "60"
    assert snapshot["values"]["warranty.goods.terms"] == "Условия продукта"
