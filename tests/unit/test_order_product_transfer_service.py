from __future__ import annotations

from pathlib import Path

import pytest

from models import OrderProductLink, Product
from services.order_product_transfer_service import OrderProductTransferService


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _ScalarResult:
    def __init__(self, product: Product):
        self._product = product

    def scalars(self):
        return self

    def first(self):
        return self._product

    def all(self):
        return [self._product]


class _ProductSession:
    def __init__(self, product: Product):
        self.product = product
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _ScalarResult(self.product)


def _product(*, title: str) -> Product:
    return Product(
        id=17,
        title=title,
        slug="stable-product-slug",
        source_url="https://example.com/stable-product",
        price=9000,
        specs={},
        is_published=True,
    )


@pytest.mark.asyncio
async def test_legacy_none_title_snapshot_survives_renamed_product_roundtrip():
    exported_product = _product(title="Catalog title at export")
    legacy_link = OrderProductLink(
        id=31,
        order_id=10,
        proposal_id=20,
        product_id=17,
        quantity=1,
        price=3200,
        title_snapshot=None,
        currency_snapshot=None,
    )
    legacy_link.product = exported_product

    transferred_line = OrderProductTransferService.snapshot_line(legacy_link)
    assert transferred_line.product.title == "Catalog title at export"
    assert transferred_line.title_snapshot is None

    renamed_product = _product(title="Catalog title after rename")
    resolved = await OrderProductTransferService.resolve_product(
        _ProductSession(renamed_product),
        transferred_line.product,
    )
    assert resolved.product is renamed_product
    assert resolved.reason == "slug"

    imported_link = OrderProductTransferService.build_import_link(
        order_id=40,
        proposal_id=50,
        product_line=transferred_line,
        product=renamed_product,
    )

    assert imported_link.product_id == renamed_product.id
    assert imported_link.title_snapshot is None
    assert imported_link.currency_snapshot is None


def test_product_reference_title_is_separate_from_historical_snapshot():
    product = _product(title="Current catalog title")
    link = OrderProductLink(
        id=31,
        product_id=17,
        quantity=1,
        price=3200,
        title_snapshot="Historical checkout title",
        currency_snapshot="BYN",
    )
    link.product = product

    transferred_line = OrderProductTransferService.snapshot_line(link)

    assert transferred_line.product.title == "Current catalog title"
    assert transferred_line.title_snapshot == "Historical checkout title"


def test_order_transfer_modules_stay_below_monolith_gate():
    for relative_path in (
        "services/order_transfer_service.py",
        "services/order_product_transfer_service.py",
    ):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert len(source.splitlines()) < 700
