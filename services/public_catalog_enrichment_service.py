"""Attach reusable knowledge and compatible offers to visible public products."""

from sqlalchemy.ext.asyncio import AsyncSession

from models import Product
from models.tenancy import TenantScope
from services.catalog_accessory_service import CatalogAccessoryService
from services.catalog_document_service import CatalogDocumentService


async def enrich_public_products(
    session: AsyncSession, products: list[Product], *, tenant_scope: TenantScope,
) -> None:
    """Call after storefront visibility resolution, before synchronous mapping."""
    if not products:
        return
    documents = await CatalogDocumentService.resolve_for_products(
        session, products, public_only=True,
    )
    accessories = await CatalogAccessoryService.resolve_public(
        session, products, tenant_scope=tenant_scope,
    )
    for product in products:
        product.__dict__["_catalog_documents"] = documents.get(int(product.id), [])
        product.__dict__["_catalog_accessories"] = accessories.get(int(product.id), [])
