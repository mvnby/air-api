"""Manager-only installation estimate confirmation and proposal attachment."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.public_write_idempotency import get_required_public_write_idempotency_key
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    ATTACH_MANAGER_INSTALLATION_ESTIMATE, CONFIRM_MANAGER_INSTALLATION_ESTIMATE,
    GET_MANAGER_INSTALLATION_ESTIMATE_REVISION, PREVIEW_MANAGER_INSTALLATION_ESTIMATE,
    RESOLVE_MANAGER_INSTALLATION_TARIFF,
    LIST_MANAGER_INSTALLATION_STANDARD_TARIFFS,
    SUGGEST_MANAGER_INSTALLATION_STANDARD_TARIFFS,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_installation_confirmation import (
    ManagerInstallationAttachPayload, ManagerInstallationAttachResponse,
    ManagerInstallationConfirmPayload, ManagerInstallationConfirmResponse,
    ManagerInstallationEstimateRevisionResponse,
    ManagerInstallationPreviewResponse,
    ManagerInstallationPreviewPayload, ManagerInstallationStandardTariffList,
    ManagerInstallationStandardSuggestionsPayload, ManagerInstallationStandardSuggestionsResponse,
)
from schemas_installation_price_book import (
    InstallationPreviewPayload, InstallationPreviewResponse,
    InstallationResolvePayload, InstallationResolveResponse,
)
from services.installation_estimate_confirmation_service import (
    InstallationEstimateConfirmationService, InstallationPriceChanged,
)
from services.installation_price_book_service import InstallationPriceBookService
from services.installation_standard_catalogue_service import list_standard_tariffs, suggest_standard_tariffs
from services.public_write_idempotency_service import (
    PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable,
)


router = APIRouter(
    prefix="/api/manager/installation-estimates",
    tags=["manager/installation-estimates"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


def _manager_preview(result: InstallationPreviewResponse) -> ManagerInstallationPreviewResponse:
    lines = {}
    if result.status == "fixed":
        for mode in ("collapsed", "detailed"):
            projected, _ = InstallationEstimateConfirmationService.project_preview(result, mode)
            lines[f"{mode}_lines"] = [{"title": title, "price": price} for title, price in projected]
        from services.installation_estimate_projection import grouped_installation_lines
        lines["collapsed_lines"] = grouped_installation_lines(result)
    return ManagerInstallationPreviewResponse(**result.model_dump(), **lines)


def _idempotency_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PublicWriteIdempotencyConflict):
        return HTTPException(status_code=409, detail={"code": "idempotency_key_reused"})
    return HTTPException(status_code=503, detail={"code": "idempotency_unavailable"},
                         headers={"Retry-After": "1"})


@router.get("/standard-tariffs", response_model=ManagerInstallationStandardTariffList,
            operation_id=LIST_MANAGER_INSTALLATION_STANDARD_TARIFFS)
async def list_manager_installation_standard_tariffs(
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read fixed standard complete-split-system tariffs from the tenant’s published price
    book, using capacity-only or type-only matching. Strict product matches are excluded.
    With no published book the response contains no revision and no items. These suggestions
    are for free commercial rows; reading them does not bind equipment or confirm an
    estimate.

    Access and scope: Manager access is required; published installation pricing belongs to
    the authenticated tenant, independently of storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await list_standard_tariffs(session, scope)


@router.post("/standard-suggestions", response_model=ManagerInstallationStandardSuggestionsResponse,
             operation_id=SUGGEST_MANAGER_INSTALLATION_STANDARD_TARIFFS)
async def suggest_manager_installation_standard_tariffs(
    payload: ManagerInstallationStandardSuggestionsPayload,
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Resolve standard installation suggestions for at most 100 submitted visible catalog
    products against the tenant’s current published book. Unknown/inaccessible products and
    incomplete, ambiguous or unmatched profiles are omitted; repeated product IDs are
    deduplicated. This reads suggestions without creating an estimate, equipment claim or
    proposal line.

    Access and scope: Manager access is required; published installation pricing belongs to
    the authenticated tenant, independently of storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await suggest_standard_tariffs(session, scope, payload.product_ids)


@router.post("/resolve", response_model=InstallationResolveResponse,
             operation_id=RESOLVE_MANAGER_INSTALLATION_TARIFF)
async def resolve_manager_installation_tariff(
    payload: InstallationResolvePayload,
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Resolve installation input against the tenant’s current published book and return
    fixed/from/provisional/quote/unavailable status with its reason. Missing published book
    produces quote with price_book_not_published rather than a fabricated price. No preview
    snapshot, estimate or proposal line is saved.

    Access and scope: Manager access is required; published installation pricing belongs to
    the authenticated tenant, independently of storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    result, _ = await InstallationPriceBookService.resolve(
        session, scope, payload,
    )
    return result


@router.post("/preview", response_model=ManagerInstallationPreviewResponse,
             operation_id=PREVIEW_MANAGER_INSTALLATION_ESTIMATE)
async def preview_manager_installation_estimate(
    payload: ManagerInstallationPreviewPayload,
    idempotency_key: str = Depends(get_required_public_write_idempotency_key),
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Calculate installation pricing; fixed/from results save a preview snapshot with opaque
    preview_ref valid for 30 minutes, while quote/unresolved results may have no snapshot.
    Idempotency-Key is required: an unexpired saved key/input replays and changed input
    under that key returns 409. expected_revision mismatch returns 409 price_changed;
    receipt contention/unavailable preview reference returns 503 with Retry-After. Expired
    keys can produce a fresh calculation. This does not accept a price or add order lines;
    only fixed previews can subsequently be confirmed.

    Access and scope: Manager access is required; pricing uses the authenticated tenant’s
    book and saved previews belong to that tenant and the selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    result = await InstallationPriceBookService.preview(
        session, scope, payload, idempotency_key=idempotency_key,
        tariff_selections=payload.tariff_selections,
    )
    return _manager_preview(result)


@router.post("/confirm", response_model=ManagerInstallationConfirmResponse,
             status_code=201, operation_id=CONFIRM_MANAGER_INSTALLATION_ESTIMATE)
async def confirm_manager_installation_estimate(
    payload: ManagerInstallationConfirmPayload,
    response: Response,
    idempotency_key: str = Depends(get_required_public_write_idempotency_key),
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
    actor: str = Depends(get_current_username),
):
    """
    Accept a fixed, unexpired preview as an immutable estimate revision for the scoped
    order/proposal, verifying equipment identity and any explicitly verified service-only
    profiles. Idempotency-Key is required; same key/payload replays and changed payload
    returns 409. Missing target/preview returns 404; non-fixed/expired preview or
    sent/approved proposal returns 409. A changed price book returns 409 price_changed with
    a fresh preview requiring new consent; unavailable receipt storage returns 503 with
    Retry-After. This saves the accepted estimate; proposal service lines are added
    separately by attach.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    try:
        outcome = await InstallationEstimateConfirmationService.confirm(
            session, scope, payload, idempotency_key=idempotency_key, actor=actor,
        )
    except InstallationPriceChanged as exc:
        fresh_payload = exc.payload.model_copy(update={"expected_revision": None})
        fresh = await InstallationPriceBookService.preview(
            session, scope, fresh_payload, idempotency_key=secrets.token_urlsafe(32),
            tariff_selections=getattr(fresh_payload, "tariff_selections", {}),
        )
        raise HTTPException(status_code=409, detail={
            "code": "price_changed", "current_revision": exc.current_revision,
            "fresh_preview": _manager_preview(fresh).model_dump(mode="json"), "new_consent_required": True,
        }) from exc
    except (PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable) as exc:
        raise _idempotency_error(exc) from exc
    response.status_code = outcome.status_code
    return outcome.value


@router.get("/{estimate_id}/revisions/{revision}",
            response_model=ManagerInstallationEstimateRevisionResponse,
            operation_id=GET_MANAGER_INSTALLATION_ESTIMATE_REVISION)
async def get_manager_installation_estimate_revision(
    estimate_id: int, revision: int,
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read one immutable accepted installation estimate revision and its factual
    pricing/confirmation snapshot. Missing or out-of-scope estimate/revision returns 404.
    Current tariff edits and price-book publication do not recalculate these saved amounts.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await InstallationEstimateConfirmationService.get_revision(
        session, scope, estimate_id, revision,
    )


@router.post("/{estimate_id}/orders/{order_id}/proposals/{proposal_id}/attach",
             response_model=ManagerInstallationAttachResponse,
             operation_id=ATTACH_MANAGER_INSTALLATION_ESTIMATE)
async def attach_manager_installation_estimate(
    estimate_id: int, order_id: int, proposal_id: int,
    payload: ManagerInstallationAttachPayload,
    response: Response,
    idempotency_key: str = Depends(get_required_public_write_idempotency_key),
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Add accepted installation revision lines to its original scoped order/proposal in
    collapsed or detailed projection, preserving the accepted total and recalculating order
    financials. Idempotency-Key is required; changed payload under the key returns 409 and
    receipt unavailability 503 with Retry-After. Missing or mismatched estimate/target
    returns 404; conflicting existing projection, duplicate installation identity or
    noneditable proposal returns 409. An identical existing attachment is reused; a new
    attachment requires an editable proposal. This writes proposal lines without rerunning
    current pricing.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    try:
        outcome = await InstallationEstimateConfirmationService.attach(
            session, scope, order_id=order_id, proposal_id=proposal_id,
            estimate_id=estimate_id, payload=payload, idempotency_key=idempotency_key,
        )
    except (PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable) as exc:
        raise _idempotency_error(exc) from exc
    response.status_code = outcome.status_code
    return outcome.value
