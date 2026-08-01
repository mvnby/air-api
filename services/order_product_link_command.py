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


@dataclass(frozen=True)
class OrderProductCatalogSnapshot:
    product_id: int
    title: str
    unit_price: int
    currency: str
    pricing_source: str

    def __post_init__(self) -> None:
        product_id = int(self.product_id)
        title = " ".join(str(self.title or "").split())
        unit_price = int(self.unit_price)
        currency = str(self.currency or "").strip().upper()
        pricing_source = str(self.pricing_source or "").strip()
        if product_id <= 0:
            raise ValueError("product_id must be positive")
        if not title:
            raise ValueError("title snapshot is required")
        if unit_price < 0:
            raise ValueError("unit price snapshot must be non-negative")
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency snapshot must be a three-letter code")
        if pricing_source not in {"shared_product", "tenant_offer"}:
            raise ValueError("unsupported pricing snapshot source")
        object.__setattr__(self, "product_id", product_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "unit_price", unit_price)
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "pricing_source", pricing_source)

    def as_technical_meta(self) -> dict[str, int | str]:
        return {
            "product_id": self.product_id,
            "title_snapshot": self.title,
            "unit_price": self.unit_price,
            "currency_snapshot": self.currency,
            "source": self.pricing_source,
        }


class OrderProductLinkCommand:
    """Construct links from shared products or locked storefront snapshots."""

    def __init__(
        self,
        snapshots: Mapping[int, OrderProductCatalogSnapshot] | None = None,
        *,
        shared_currency: str = "BYN",
    ) -> None:
        self._snapshots = (
            None
            if snapshots is None
            else MappingProxyType(
                {
                    int(product_id): snapshot
                    for product_id, snapshot in snapshots.items()
                }
            )
        )
        if self._snapshots is not None:
            for product_id, snapshot in self._snapshots.items():
                if product_id != snapshot.product_id:
                    raise ValueError("snapshot key must match product_id")
        normalized_currency = str(shared_currency or "").strip().upper()
        if len(normalized_currency) != 3 or not normalized_currency.isalpha():
            raise ValueError("shared currency must be a three-letter code")
        self._shared_currency = normalized_currency

    @classmethod
    def shared_catalog(cls) -> "OrderProductLinkCommand":
        return cls()

    @classmethod
    def storefront_snapshot(
        cls,
        snapshots: Mapping[int, OrderProductCatalogSnapshot],
    ) -> "OrderProductLinkCommand":
        return cls(snapshots)

    @property
    def unit_prices(self) -> Mapping[int, int] | None:
        if self._snapshots is None:
            return None
        return MappingProxyType(
            {
                product_id: snapshot.unit_price
                for product_id, snapshot in self._snapshots.items()
            }
        )

    @property
    def snapshots(self) -> Mapping[int, OrderProductCatalogSnapshot] | None:
        return self._snapshots

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
        if self._snapshots is None:
            snapshot = OrderProductCatalogSnapshot(
                product_id=product_id,
                title=product.title,
                unit_price=int(product.price),
                currency=self._shared_currency,
                pricing_source="shared_product",
            )
        else:
            snapshot = self._snapshots[product_id]
        unit_price = snapshot.unit_price
        quantity = item["quantity"]
        with_installation = bool(item.get("with_installation", False))
        installation_price = int(item.get("installation_price", 0))
        link = OrderProductLink(
            order_id=order_id,
            proposal_id=proposal_id,
            product_id=product_id,
            quantity=quantity,
            price=unit_price,
            title_snapshot=snapshot.title,
            currency_snapshot=snapshot.currency,
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
