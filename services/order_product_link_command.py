"""Focused command for immutable order-product price/link snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from models import OrderProductLink, Product


@dataclass(frozen=True)
class OrderProductLinkMutation:
    link: OrderProductLink
    product_total: int


class OrderProductLinkCommand:
    """Construct a link from either shared or pre-locked storefront prices."""

    def __init__(self, unit_prices: Mapping[int, int] | None = None) -> None:
        self._unit_prices = (
            None
            if unit_prices is None
            else MappingProxyType(
                {
                    int(product_id): int(unit_price)
                    for product_id, unit_price in unit_prices.items()
                }
            )
        )

    @classmethod
    def shared_catalog(cls) -> "OrderProductLinkCommand":
        return cls()

    @classmethod
    def storefront_snapshot(
        cls,
        unit_prices: Mapping[int, int],
    ) -> "OrderProductLinkCommand":
        return cls(unit_prices)

    @property
    def unit_prices(self) -> Mapping[int, int] | None:
        return self._unit_prices

    def build(
        self,
        *,
        order_id: int,
        proposal_id: int,
        product: Product,
        item: Mapping[str, Any],
        product_cost: int,
    ) -> OrderProductLinkMutation:
        product_id = int(product.id)
        unit_price = (
            int(product.price)
            if self._unit_prices is None
            else int(self._unit_prices[product_id])
        )
        quantity = item["quantity"]
        with_installation = bool(item.get("with_installation", False))
        installation_price = int(item.get("installation_price", 0))
        link = OrderProductLink(
            order_id=order_id,
            proposal_id=proposal_id,
            product_id=product_id,
            quantity=quantity,
            price=unit_price,
            cost=product_cost,
            is_installation_included=with_installation,
            installation_price=installation_price if with_installation else 0,
            installation_details=(
                item.get("installation_meta") if with_installation else None
            ),
        )
        return OrderProductLinkMutation(
            link=link,
            product_total=unit_price * quantity,
        )
