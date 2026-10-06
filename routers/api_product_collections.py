from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.product_collections import PublicProductCollectionPlacementResponse
from core.database import get_session
from core.tenant_scope import get_public_tenant_scope, verify_public_storefront_request
from models.tenancy import TenantScope
from services.product_collection_resolver import ProductCollectionResolver


router = APIRouter(
    tags=["api"],
    dependencies=[Depends(verify_public_storefront_request)],
)


@router.get(
    "/v1/content/placements/{surface_key}/{slot_key}/collections",
    response_model=PublicProductCollectionPlacementResponse,
    operation_id="get_public_product_collection_placement",
)
async def get_public_product_collection_placement(
    surface_key: str = Path(min_length=1, max_length=80),
    slot_key: str = Path(min_length=1, max_length=80),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Resolve published product collections for a storefront surface and slot. Keys are
    lowercased before resolution; the result contains the placement projection rather than
    editable collection definitions.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    return await ProductCollectionResolver.resolve_placement(
        session,
        surface_key=surface_key.lower(),
        slot_key=slot_key.lower(),
        tenant_scope=tenant_scope,
    )
