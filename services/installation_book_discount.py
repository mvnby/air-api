"""Keep canonical storefront book prices aligned with catalog bundle discounts."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from models.tenancy import TenantScope
from services.installation_discount_service import InstallationDiscountService
from services.product_collection_catalog_access import ProductCollectionCatalogAccess


async def catalog_bundle_discounts(
    session: AsyncSession, scope: TenantScope, product_ids: set[int],
) -> dict[int, Decimal]:
    # Partner books own their discounts; MVN's margin policy is system-owned.
    if scope.is_canonical_storefront is not True or not product_ids:
        return {}
    visible = await ProductCollectionCatalogAccess.visible_by_ids(
        session, tenant_scope=scope, product_ids=product_ids,
    )
    decisions = await InstallationDiscountService.resolve_for_products(
        session,
        products=[projection.product for projection in visible.values()],
        effective_prices={key: projection.price for key, projection in visible.items()},
    )
    return {
        key: Decimal(decisions[key].applied_discount) if key in decisions else Decimal(0)
        for key in product_ids
    }
