"""Single visibility and pricing boundary for every public product surface."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from crud.product import ProductDAO
from crud.public_catalog import PublicCatalogDAO, PublicCatalogRow
from crud.public_catalog_checkout import PublicCatalogCheckoutDAO
from models import Product
from models.tenancy import TenantScope
from services.order_product_link_command import OrderProductCatalogSnapshot
from services.tenant_scope_service import SystemTenantScopeResolver


@dataclass(frozen=True)
class PublicProductProjection:
    product: Product
    price: int
    old_price: int | None

    @property
    def pricing(self) -> tuple[int, int | None]:
        return self.price, self.old_price


class PublicCatalogVisibilityService:
    """Canonical MVN sees published products; other storefronts need an offer."""

    @staticmethod
    async def is_canonical_scope(
        session: AsyncSession,
        tenant_scope: TenantScope,
    ) -> bool:
        if tenant_scope.is_canonical_storefront is not None:
            return tenant_scope.is_canonical_storefront
        canonical = await SystemTenantScopeResolver.resolve(session)
        return (
            tenant_scope.tenant_id == canonical.tenant_id
            and tenant_scope.storefront_id == canonical.storefront_id
        )

    @staticmethod
    def project_row(row: PublicCatalogRow) -> PublicProductProjection:
        product, price, old_price = row
        return PublicProductProjection(
            product=product,
            price=price,
            old_price=old_price,
        )

    @staticmethod
    def project_product(product: Product) -> PublicProductProjection:
        return PublicProductProjection(
            product=product,
            price=int(product.price),
            old_price=(int(product.old_price) if product.old_price is not None else None),
        )

    @classmethod
    async def get_visible_product_by_id(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        product_id: int,
    ) -> PublicProductProjection | None:
        if await cls.is_canonical_scope(session, tenant_scope):
            product = await ProductDAO.get_by_id(
                session,
                product_id,
                is_published=True,
            )
            if product is None:
                return None
            return cls.project_product(product)

        rows = await PublicCatalogDAO.get_by_ids(
            session,
            tenant_scope=tenant_scope,
            product_ids=[product_id],
        )
        return cls.project_row(rows[0]) if rows else None

    @classmethod
    async def get_checkout_snapshots(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        product_ids: set[int],
    ) -> dict[int, OrderProductCatalogSnapshot]:
        if await cls.is_canonical_scope(session, tenant_scope):
            rows = await PublicCatalogCheckoutDAO.get_shared_snapshots_by_ids(
                session,
                tenant_scope=tenant_scope,
                product_ids=product_ids,
            )
            source = "shared_product"
        else:
            rows = await PublicCatalogCheckoutDAO.get_offer_snapshots_by_ids(
                session,
                tenant_scope=tenant_scope,
                product_ids=product_ids,
            )
            source = "tenant_offer"
        return {
            product_id: OrderProductCatalogSnapshot(
                product_id=row.product_id,
                title=row.title,
                unit_price=row.unit_price,
                currency=row.currency,
                pricing_source=source,
            )
            for product_id, row in rows.items()
        }
