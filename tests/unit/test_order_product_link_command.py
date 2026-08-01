from __future__ import annotations

import pytest
from sqlalchemy import Text

from models import OrderProductLink, Product
from schemas_manager_orders import OrderProductLineResponse
from services.order_product_link_command import (
    OrderProductCatalogSnapshot,
    OrderProductLinkCommand,
)
from services.order_projection_service import OrderProjectionService


def _product() -> Product:
    return Product(
        id=17,
        title="Public product",
        slug="public-product",
        price=9000,
        specs={},
        is_published=True,
    )


def test_shared_catalog_command_snapshots_product_price_and_link_fields():
    mutation = OrderProductLinkCommand.shared_catalog().build(
        order_id=10,
        proposal_id=20,
        product=_product(),
        item={
            "product_id": 17,
            "quantity": 2,
            "with_installation": True,
            "installation_price": 750,
            "installation_meta": {"meters": 4},
        },
        product_cost=1234,
    )

    assert mutation.link.price == 9000
    assert mutation.link.title_snapshot == "Public product"
    assert mutation.link.currency_snapshot == "BYN"
    assert mutation.link.cost == 1234
    assert mutation.link.quantity == 2
    assert mutation.link.installation_price == 750
    assert mutation.link.installation_details == {"meters": 4}
    assert mutation.product_total == 18000


def test_storefront_command_uses_exact_locked_catalog_snapshot():
    snapshot = OrderProductCatalogSnapshot(
        product_id=17,
        title="Public title at checkout",
        unit_price=3200,
        currency="eur",
        pricing_source="tenant_offer",
    )
    mutation = OrderProductLinkCommand.storefront_snapshot({17: snapshot}).build(
        order_id=10,
        proposal_id=20,
        product=_product(),
        item={"product_id": 17, "quantity": 3},
        product_cost=1234,
    )

    assert mutation.link.price == 3200
    assert mutation.link.title_snapshot == "Public title at checkout"
    assert mutation.link.currency_snapshot == "EUR"
    assert mutation.product_total == 9600


def test_storefront_command_never_falls_back_when_snapshot_is_missing():
    command = OrderProductLinkCommand.storefront_snapshot(
        {
            18: OrderProductCatalogSnapshot(
                product_id=18,
                title="Other product",
                unit_price=3200,
                currency="BYN",
                pricing_source="tenant_offer",
            )
        }
    )

    with pytest.raises(KeyError):
        command.build(
            order_id=10,
            proposal_id=20,
            product=_product(),
            item={"product_id": 17, "quantity": 1},
            product_cost=1234,
        )


def test_storefront_command_rejects_mismatched_snapshot_key():
    snapshot = OrderProductCatalogSnapshot(
        product_id=17,
        title="Public product",
        unit_price=3200,
        currency="BYN",
        pricing_source="shared_product",
    )

    with pytest.raises(ValueError, match="snapshot key"):
        OrderProductLinkCommand.storefront_snapshot({18: snapshot})


def test_manager_product_line_dto_prefers_immutable_title_snapshot():
    changed_product = _product()
    changed_product.title = "Renamed after checkout"
    link = OrderProductLink(
        id=31,
        order_id=10,
        proposal_id=20,
        product_id=17,
        quantity=2,
        price=3200,
        title_snapshot="Public title at checkout",
        currency_snapshot="BYN",
        cost=1000,
    )
    link.product = changed_product

    payload = OrderProjectionService._map_product_line(link)
    response = OrderProductLineResponse.model_validate(payload)

    assert response.product_title == "Public title at checkout"
    assert response.title_snapshot == "Public title at checkout"
    assert response.currency_snapshot == "BYN"


def test_snapshot_preserves_unbounded_valid_product_title_exactly():
    long_title = "  " + ("Товар " * 110) + "\n"
    assert len(long_title) > 500
    product = _product()
    product.title = long_title

    mutation = OrderProductLinkCommand.shared_catalog().build(
        order_id=10,
        proposal_id=20,
        product=product,
        item={"product_id": 17, "quantity": 1},
        product_cost=1234,
    )

    assert mutation.link.title_snapshot == long_title
    assert isinstance(mutation.link.__table__.c.title_snapshot.type, Text)
    mutation.link.id = 32
    response = OrderProductLineResponse.model_validate(
        OrderProjectionService._map_product_line(mutation.link)
    )
    assert response.title_snapshot == long_title
    assert response.product_title == long_title
