from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, CUSTOMER_NOT_FOUND
from core.security import get_current_manager_tenant_scope
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    LOOKUP_MANAGER_CUSTOMER_POSTCODES, PREVIEW_MANAGER_CUSTOMER_ENVELOPE,
    PRINT_MANAGER_CUSTOMER_ENVELOPE,
)
from services.belpost_postcode_service import (
    PostcodeLookupUnavailable, PostcodeSearchPayload, PostcodeSearchResponse, lookup_postcodes,
)
from services.customer_service import CustomerService
from services.envelope_print_service import (
    EnvelopePreviewResponse, EnvelopePrintPayload, preview_envelope, render_envelope_pdf,
)

router = APIRouter()


@router.post(
    "/customers/{customer_id}/envelope-preview",
    operation_id=PREVIEW_MANAGER_CUSTOMER_ENVELOPE,
    response_model=EnvelopePreviewResponse,
)
async def preview_customer_envelope(
    customer_id: int,
    payload: EnvelopePrintPayload,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> EnvelopePreviewResponse:
    """
    Normalize reviewed sender and recipient addresses for a current-tenant customer's
    envelope. Returns the same postal lines used by the PDF and warnings for ambiguous
    fragments; never invents missing settlements or post offices. Missing/inaccessible
    customers return 404. No directory request, customer update or document is created.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    customer = await CustomerService.get_for_manager(session, customer_id, tenant_scope=tenant_scope)
    if customer is None:
        raise manager_http_error(status_code=404, endpoint=PREVIEW_MANAGER_CUSTOMER_ENVELOPE,
                                 error_code=CUSTOMER_NOT_FOUND, message="Клиент не найден")
    response.headers["Cache-Control"] = "no-store"
    return preview_envelope(payload)


@router.post(
    "/customers/{customer_id}/envelope-postcodes",
    operation_id=LOOKUP_MANAGER_CUSTOMER_POSTCODES,
    response_model=PostcodeSearchResponse,
)
async def lookup_customer_postcodes(
    customer_id: int,
    payload: PostcodeSearchPayload,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> PostcodeSearchResponse:
    """
    Query the public Belpost address directory on explicit Manager request for a current-
    tenant customer. Returns up to 100 suggestions with served houses for manual selection;
    no candidate is applied or persisted. Missing/inaccessible customers return 404;
    provider failures return 502 and manual postcode entry remains available.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    customer = await CustomerService.get_for_manager(session, customer_id, tenant_scope=tenant_scope)
    if customer is None:
        raise manager_http_error(status_code=404, endpoint=LOOKUP_MANAGER_CUSTOMER_POSTCODES,
                                 error_code=CUSTOMER_NOT_FOUND, message="Клиент не найден")
    response.headers["Cache-Control"] = "no-store"
    try:
        return await lookup_postcodes(payload.address)
    except PostcodeLookupUnavailable as exc:
        raise manager_http_error(status_code=502, endpoint=LOOKUP_MANAGER_CUSTOMER_POSTCODES,
                                 error_code=BAD_REQUEST, message=str(exc)) from exc


@router.post(
    "/customers/{customer_id}/envelope-pdf",
    operation_id=PRINT_MANAGER_CUSTOMER_ENVELOPE,
    response_class=Response,
    responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
)
async def print_customer_envelope(
    customer_id: int,
    payload: EnvelopePrintPayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> Response:
    """
    Render a single DL (default), C6, C5 or C4 envelope at actual size for a current-tenant
    customer using explicitly reviewed
    sender/recipient names, addresses and six-digit Belarusian postcodes. Orders postal
    lines from specific to general; optional bounded PNG/JPEG branding stays in the
    lower-left area. Missing or
    foreign-tenant customers return 404; overflowing text returns 400. This stateless
    print operation does not change customer requisites or create a business document.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    customer = await CustomerService.get_for_manager(session, customer_id, tenant_scope=tenant_scope)
    if customer is None:
        raise manager_http_error(status_code=404, endpoint=PRINT_MANAGER_CUSTOMER_ENVELOPE,
                                 error_code=CUSTOMER_NOT_FOUND, message="Клиент не найден")
    try:
        content = await run_in_threadpool(render_envelope_pdf, payload)
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=PRINT_MANAGER_CUSTOMER_ENVELOPE,
                                 error_code=BAD_REQUEST, message=str(exc)) from exc
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="envelope-{payload.format.lower()}-{customer_id}.pdf"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })
