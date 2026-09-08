"""Resolve read-only B2C equipment defaults from the scoped sold product."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from models import Brand, OrderProductLink, Product
from models.tenancy import TenantScope
from modules.documents.domain import ConsumerDocumentTerms, DEFAULT_GOODS_WARRANTY_MONTHS
from services.warranty_service import WarrantyService


def _text(value: object | None) -> str:
    return str(value or "").strip()


def _valid_months(value: object | None) -> int | None:
    try:
        months = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return months if 1 <= months <= 240 else None


def _single_product(links: Sequence[OrderProductLink]) -> Product | None:
    """Return the catalog product only when the supplied equipment is singular."""

    products: dict[int, Product] = {}
    for link in links:
        product_id = getattr(link, "product_id", None)
        product = getattr(link, "product", None)
        if product_id is None or product is None:
            return None
        products[int(product_id)] = product
    return next(iter(products.values())) if len(products) == 1 else None


class ConsumerEquipmentDefaultsError(ValueError):
    """The requested order or proposal cannot supply consumer defaults."""


async def resolve_consumer_equipment_defaults(
    session: AsyncSession,
    *,
    product_links: Sequence[OrderProductLink],
    terms: ConsumerDocumentTerms | None = None,
    issue_date: date,
) -> ConsumerDocumentTerms:
    """Merge operator-entered B2C terms with defaults for one sold catalog SKU.

    A serial number is intentionally never inferred. A warranty of zero is an
    explicit operator opt-out and is therefore preserved.
    """

    resolved = terms or ConsumerDocumentTerms()
    product = _single_product(product_links)
    if product is None:
        return replace(
            resolved,
            equipment_serial=_text(resolved.equipment_serial) or None,
            goods_warranty_months=(
                resolved.goods_warranty_months
                if resolved.goods_warranty_months is not None
                else DEFAULT_GOODS_WARRANTY_MONTHS
            ),
        )

    brand = await session.get(Brand, int(product.brand_id)) if product.brand_id else None
    brand_title = _text(getattr(brand, "title", None))
    model = _text(getattr(product, "title", None)) or next(
        (
            _text(getattr(link, "title_snapshot", None))
            for link in product_links
            if _text(getattr(link, "title_snapshot", None))
        ),
        "",
    )

    goods_months = resolved.goods_warranty_months
    goods_terms = resolved.goods_warranty_terms
    if goods_months is None:
        policy = await WarrantyService.resolve_policy(
            session,
            product=product,
            supplier_id=None,
            coverage_type="supplier",
            at=datetime.combine(issue_date, time.min),
        )
        policy_months = _valid_months(getattr(policy, "duration_months", None))
        if policy_months is not None:
            goods_months = policy_months
            if not _text(goods_terms):
                goods_terms = _text(getattr(policy, "terms", None)) or None
        else:
            goods_months = _valid_months(
                WarrantyService._warranty_months_from_product(product)
            ) or DEFAULT_GOODS_WARRANTY_MONTHS

    return replace(
        resolved,
        equipment_brand=_text(resolved.equipment_brand) or brand_title or None,
        equipment_model=_text(resolved.equipment_model) or model or None,
        equipment_serial=_text(resolved.equipment_serial) or None,
        goods_warranty_months=goods_months,
        goods_warranty_terms=_text(goods_terms) or None,
    )


async def resolve_consumer_equipment_defaults_for_order(
    session: AsyncSession,
    *,
    tenant_scope: TenantScope,
    order_id: int,
    proposal_id: int | None,
    terms: ConsumerDocumentTerms | None = None,
    issue_date: date | None = None,
) -> ConsumerDocumentTerms:
    """Load a tenant-scoped order, select its proposal, and resolve its defaults."""

    # Kept local because DocumentContextBuilder uses this module when freezing
    # a draft snapshot; importing it at module load time would create a cycle.
    from .context_builder import DocumentContextBuilder, DocumentContextError

    order = await DocumentContextBuilder._load_order(
        session,
        order_id=order_id,
        tenant_scope=tenant_scope,
    )
    if order is None:
        raise ConsumerEquipmentDefaultsError("Заказ не найден")
    try:
        _, product_links, _ = DocumentContextBuilder._select_proposal_lines(
            order,
            proposal_id,
        )
    except DocumentContextError as exc:
        raise ConsumerEquipmentDefaultsError(str(exc)) from exc
    return await resolve_consumer_equipment_defaults(
        session,
        product_links=product_links,
        terms=terms,
        issue_date=issue_date or date.today(),
    )
