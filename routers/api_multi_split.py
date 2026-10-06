"""Public, price-only multi-split options and server-verified preview."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.multi_split import MultiSplitLeadPayload, MultiSplitLeadResponse, MultiSplitOptionsResponse, MultiSplitPreviewRequest, MultiSplitPreviewResponse
from core.database import get_session
from core.public_write_idempotency import get_required_public_write_idempotency_key
from core.tenant_scope import get_public_tenant_scope, verify_public_storefront_request
from models.tenancy import TenantScope
from services.multi_split_configuration_service import MultiSplitConfigurationService, MultiSplitSelectionError
from services.multi_split_lead_service import MultiSplitLeadService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable

router = APIRouter(prefix="/v1/multi-split", tags=["multi-split"])


@router.get("/options", response_model=MultiSplitOptionsResponse, operation_id="list_public_multi_split_options")
async def list_public_multi_split_options(
    kind: Literal["outdoor_unit", "indoor_unit"],
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    List storefront-visible indoor or outdoor units for multi-split selection, with public
    prices and pagination; limit is at most 100.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    return await MultiSplitConfigurationService.list_options(
        session, tenant_scope=tenant_scope, kind=kind, page=page, limit=limit,
    )


@router.post("/preview", response_model=MultiSplitPreviewResponse, operation_id="preview_public_multi_split")
async def preview_public_multi_split(
    payload: MultiSplitPreviewRequest,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Validate a multi-split selection server-side in the resolved storefront and return its
    public price projection without creating a lead. Invalid or incompatible selection
    returns 422.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    try:
        preview = await MultiSplitConfigurationService.preview(
            session, tenant_scope=tenant_scope, request=payload,
        )
    except MultiSplitSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return preview.public


@router.post(
    "/leads",
    response_model=MultiSplitLeadResponse,
    operation_id="create_public_multi_split_lead",
    dependencies=[Depends(verify_public_storefront_request)],
)
async def create_public_multi_split_lead(
    payload: MultiSplitLeadPayload,
    idempotency_key: str = Depends(get_required_public_write_idempotency_key),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Validate a multi-split selection and create a lead in this storefront. Idempotency-Key
    is required; invalid selection or intake values return 422. For required keys, unsigned
    compatibility, conflicting payloads (409) and retries after 503 with Retry-After, see
    [public write
    idempotency](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#public-write-idempotency).
    Retain the same key and content when retrying.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    try:
        return await MultiSplitLeadService.create(
            session, tenant_scope=tenant_scope, payload=payload, idempotency_key=idempotency_key,
        )
    except PublicWriteIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PublicWriteIdempotencyUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "1"}) from exc
    except (MultiSplitSelectionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
