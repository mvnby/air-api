from __future__ import annotations

import pytest

from models import Product
from services.order_product_link_command import OrderProductLinkCommand


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
    assert mutation.link.cost == 1234
    assert mutation.link.quantity == 2
    assert mutation.link.installation_price == 750
    assert mutation.link.installation_details == {"meters": 4}
    assert mutation.product_total == 18000


def test_storefront_command_uses_exact_locked_price_snapshot():
    mutation = OrderProductLinkCommand.storefront_snapshot({17: 3200}).build(
        order_id=10,
        proposal_id=20,
        product=_product(),
        item={"product_id": 17, "quantity": 3},
        product_cost=1234,
    )

    assert mutation.link.price == 3200
    assert mutation.product_total == 9600


def test_storefront_command_never_falls_back_when_snapshot_is_missing():
    command = OrderProductLinkCommand.storefront_snapshot({18: 3200})

    with pytest.raises(KeyError):
        command.build(
            order_id=10,
            proposal_id=20,
            product=_product(),
            item={"product_id": 17, "quantity": 1},
            product_cost=1234,
        )
