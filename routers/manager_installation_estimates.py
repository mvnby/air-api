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
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_installation_confirmation import (
    ManagerInstallationAttachPayload, ManagerInstallationAttachResponse,
    ManagerInstallationConfirmPayload, ManagerInstallationConfirmResponse,
    ManagerInstallationEstimateRevisionResponse,
    ManagerInstallationPreviewResponse,
    ManagerInstallationPreviewPayload, ManagerInstallationStandardTariffList,
)
from schemas_installation_price_book import (
    InstallationPreviewPayload, InstallationPreviewResponse,
    InstallationResolvePayload, InstallationResolveResponse,
)
from services.installation_estimate_confirmation_service import (
    InstallationEstimateConfirmationService, InstallationPriceChanged,
)
from services.installation_price_book_service import InstallationPriceBookService
from services.installation_standard_catalogue_service import list_standard_tariffs
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
    return await list_standard_tariffs(session, scope)


@router.post("/resolve", response_model=InstallationResolveResponse,
             operation_id=RESOLVE_MANAGER_INSTALLATION_TARIFF)
async def resolve_manager_installation_tariff(
    payload: InstallationResolvePayload,
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
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
    try:
        outcome = await InstallationEstimateConfirmationService.attach(
            session, scope, order_id=order_id, proposal_id=proposal_id,
            estimate_id=estimate_id, payload=payload, idempotency_key=idempotency_key,
        )
    except (PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable) as exc:
        raise _idempotency_error(exc) from exc
    response.status_code = outcome.status_code
    return outcome.value
