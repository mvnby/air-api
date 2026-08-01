"""Focused product-line mapping for portable Manager order transfers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import OrderProductLink, Product
from schemas import (
    ManagerOrderTransferProductLine,
    ManagerOrderTransferProductRef,
)
from services.order_service import OrderService


@dataclass(frozen=True)
class ResolvedTransferProduct:
    product: Product | None
    status: str
    reason: str | None = None


class OrderProductTransferService:
    """Own product matching and immutable line snapshot round-trips."""

    @staticmethod
    def _optional_clean(value: Any) -> str | None:
        cleaned = " ".join(str(value or "").split())
        return cleaned or None

    @staticmethod
    def product_ref(link: OrderProductLink) -> ManagerOrderTransferProductRef:
        product = link.product
        return ManagerOrderTransferProductRef(
            source_id=product.id if product else link.product_id,
            # This is the mutable catalog reference used for display/matching.
            # The immutable order title remains a separate nullable field.
            title=(
                product.title
                if product
                else (
                    getattr(link, "title_snapshot", None)
                    or f"Товар #{link.product_id}"
                )
            ),
            slug=product.slug if product else None,
            source_url=product.source_url if product else None,
        )

    @staticmethod
    def snapshot_line(
        link: OrderProductLink,
    ) -> ManagerOrderTransferProductLine:
        return ManagerOrderTransferProductLine(
            source_id=link.id,
            product=OrderProductTransferService.product_ref(link),
            title_snapshot=getattr(link, "title_snapshot", None),
            currency_snapshot=getattr(link, "currency_snapshot", None),
            quantity=int(link.quantity or 1),
            price=int(link.price or 0),
            cost=int(link.cost or 0),
            is_installation_included=bool(link.is_installation_included),
            installation_price=int(link.installation_price or 0),
            installation_details=link.installation_details,
            logistics_components=(
                OrderService._serialize_order_logistics_components(
                    link.logistics_components
                )
            ),
        )

    @staticmethod
    async def resolve_product(
        session: AsyncSession,
        product_ref: ManagerOrderTransferProductRef,
    ) -> ResolvedTransferProduct:
        slug = OrderProductTransferService._optional_clean(product_ref.slug)
        if slug:
            result = await session.execute(
                select(Product).where(Product.slug == slug).limit(1)
            )
            product = result.scalars().first()
            if product:
                return ResolvedTransferProduct(
                    product=product,
                    status="matched",
                    reason="slug",
                )

        source_url = OrderProductTransferService._optional_clean(
            product_ref.source_url
        )
        if source_url:
            result = await session.execute(
                select(Product)
                .where(Product.source_url == source_url)
                .limit(1)
            )
            product = result.scalars().first()
            if product:
                return ResolvedTransferProduct(
                    product=product,
                    status="matched",
                    reason="source_url",
                )

        title = OrderProductTransferService._optional_clean(product_ref.title)
        if title:
            result = await session.execute(
                select(Product)
                .where(func.lower(Product.title) == title.lower())
                .limit(2)
            )
            products = list(result.scalars().all())
            if len(products) == 1:
                return ResolvedTransferProduct(
                    product=products[0],
                    status="matched",
                    reason="title",
                )
            if len(products) > 1:
                return ResolvedTransferProduct(
                    product=None,
                    status="missing",
                    reason="ambiguous_title",
                )

        return ResolvedTransferProduct(
            product=None,
            status="missing",
            reason="not_found",
        )

    @staticmethod
    def preview_match(
        *,
        source_order_id: int | None,
        product_line: ManagerOrderTransferProductLine,
        resolved: ResolvedTransferProduct,
    ) -> dict[str, Any]:
        return {
            "source_order_id": source_order_id,
            "product_title": product_line.product.title,
            "product_slug": product_line.product.slug,
            "matched_product_id": (
                resolved.product.id if resolved.product else None
            ),
            "matched_product_title": (
                resolved.product.title if resolved.product else None
            ),
            "status": resolved.status,
            "reason": resolved.reason,
        }

    @staticmethod
    def build_import_link(
        *,
        order_id: int,
        proposal_id: int,
        product_line: ManagerOrderTransferProductLine,
        product: Product,
    ) -> OrderProductLink:
        return OrderProductLink(
            order_id=order_id,
            proposal_id=proposal_id,
            product_id=int(product.id),
            quantity=int(product_line.quantity or 1),
            price=int(product_line.price or 0),
            # Preserve the exported historical fact exactly. The mutable
            # product reference above must never fabricate a legacy snapshot.
            title_snapshot=product_line.title_snapshot,
            currency_snapshot=product_line.currency_snapshot,
            cost=int(product_line.cost or 0),
            is_installation_included=bool(
                product_line.is_installation_included
            ),
            installation_price=int(product_line.installation_price or 0),
            installation_details=product_line.installation_details,
            logistics_components=[
                item.model_dump() if hasattr(item, "model_dump") else dict(item)
                for item in (product_line.logistics_components or [])
            ]
            or None,
        )
