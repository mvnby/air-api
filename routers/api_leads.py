"""Public website lead capture endpoints."""

from typing import Annotated, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from core.public_write_idempotency import (
    get_public_write_idempotency_key,
    get_required_public_write_idempotency_key,
)
from core.tenant_scope import (
    get_public_tenant_scope,
    verify_public_storefront_request,
)
from schemas_installation_estimate import (
    InstallationEstimateLeadPayload,
    InstallationEstimateLeadResponse,
)
from schemas import (
    ProductAvailabilityLeadPayload,
    ProductAvailabilityLeadResponse,
    PublicContactLeadPayload,
    PublicContactLeadResponse,
)
from services.repair_diagnostic_service import (
    RepairDiagnosticLeadResponse,
    RepairDiagnosticService,
)
from services.repair_diagnostic_intake_service import RepairDiagnosticIntakeService
from services.installation_estimate_lead_service import (
    InstallationEstimateIdempotencyConflict,
    InstallationEstimateLeadService,
    InstallationEstimateTemporarilyUnavailable,
)
from services.website_lead_service import WebsiteLeadService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict
from services.tenant_scope_service import TenantScope

router = APIRouter(
    tags=["api"],
    dependencies=[Depends(verify_public_storefront_request)],
)


async def installation_estimate_form_payload(
    name: Annotated[str, Form(min_length=1, max_length=160)],
    phone: Annotated[str, Form(min_length=7, max_length=40)],
    consent: Annotated[bool, Form()],
    email: Annotated[Optional[str], Form(max_length=254)] = None,
    address: Annotated[Optional[str], Form(max_length=500)] = None,
    description: Annotated[Optional[str], Form(max_length=2000)] = None,
    object_type: Annotated[
        Optional[str],
        Form(pattern=r"^(apartment|house|office|commercial|other)$"),
    ] = None,
) -> InstallationEstimateLeadPayload:
    try:
        return InstallationEstimateLeadPayload.model_validate(
            {
                "name": name,
                "phone": phone,
                "email": email,
                "address": address,
                "description": description,
                "object_type": object_type,
                "consent": consent,
            }
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.post(
    "/v1/leads/contact",
    response_model=PublicContactLeadResponse,
    operation_id="create_public_contact_lead",
    responses={
        400: {"description": "Invalid idempotency key"},
        409: {"description": "Idempotency key reused with different content"},
        428: {"description": "Signed write requires Idempotency-Key"},
    },
)
async def create_public_contact_lead(
    payload: PublicContactLeadPayload,
    idempotency_key: str = Depends(get_public_write_idempotency_key),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    try:
        return await WebsiteLeadService.create_contact_lead(
            session,
            payload,
            tenant_scope=tenant_scope,
            idempotency_key=idempotency_key,
        )
    except PublicWriteIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/v1/leads/installation-estimate",
    response_model=InstallationEstimateLeadResponse,
    operation_id="create_installation_estimate_lead",
    responses={
        400: {"description": "Invalid image or upload limits exceeded"},
        409: {"description": "Idempotency key reused with different content"},
        503: {"description": "Request can be retried after a short delay"},
    },
)
async def create_installation_estimate_lead(
    payload: Annotated[
        InstallationEstimateLeadPayload,
        Depends(installation_estimate_form_payload),
    ],
    idempotency_key: str = Depends(get_required_public_write_idempotency_key),
    indoor_unit: Optional[List[UploadFile]] = File(default=None),
    outdoor_unit: Optional[List[UploadFile]] = File(default=None),
    route: Optional[List[UploadFile]] = File(default=None),
    facade: Optional[List[UploadFile]] = File(default=None),
    power_supply: Optional[List[UploadFile]] = File(default=None),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    try:
        uploads = await InstallationEstimateLeadService.collect_uploads(
            {
                "indoor_unit": indoor_unit,
                "outdoor_unit": outdoor_unit,
                "route": route,
                "facade": facade,
                "power_supply": power_supply,
            }
        )
        return await InstallationEstimateLeadService.create_lead(
            session,
            payload=payload,
            uploads=uploads,
            idempotency_key=idempotency_key,
            tenant_scope=tenant_scope,
        )
    except InstallationEstimateIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InstallationEstimateTemporarilyUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Приём заявки временно занят. Повторите отправку.",
            headers={"Retry-After": "1"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/v1/leads/product-availability",
    response_model=ProductAvailabilityLeadResponse,
    operation_id="create_product_availability_lead",
    responses={
        400: {"description": "Invalid idempotency key"},
        409: {"description": "Idempotency key reused with different content"},
        428: {"description": "Signed write requires Idempotency-Key"},
    },
)
async def create_product_availability_lead(
    payload: ProductAvailabilityLeadPayload,
    idempotency_key: str = Depends(get_public_write_idempotency_key),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    try:
        return await WebsiteLeadService.create_product_availability_lead(
            session,
            payload,
            tenant_scope=tenant_scope,
            idempotency_key=idempotency_key,
        )
    except PublicWriteIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/v1/leads/repair-diagnostic",
    response_model=RepairDiagnosticLeadResponse,
    operation_id="create_repair_diagnostic_lead",
    responses={
        400: {"description": "Invalid form data or idempotency key"},
        409: {"description": "Idempotency key reused with different content"},
        428: {"description": "Signed write requires Idempotency-Key"},
    },
)
async def create_repair_diagnostic_lead(
    background_tasks: BackgroundTasks,
    idempotency_key: str = Depends(get_public_write_idempotency_key),
    payload: str = Form(...),
    nameplate: Optional[List[UploadFile]] = File(default=None),
    indoor_unit: Optional[List[UploadFile]] = File(default=None),
    outdoor_unit: Optional[List[UploadFile]] = File(default=None),
    error_display: Optional[List[UploadFile]] = File(default=None),
    leak_place: Optional[List[UploadFile]] = File(default=None),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    try:
        parsed_payload = RepairDiagnosticService.parse_payload(payload)
        uploads = await RepairDiagnosticService.collect_uploads(
            {
                "nameplate": nameplate,
                "indoor_unit": indoor_unit,
                "outdoor_unit": outdoor_unit,
                "error_display": error_display,
                "leak_place": leak_place,
            }
        )
        response, nameplate_files, replayed = await RepairDiagnosticIntakeService.create_lead(
            session,
            payload=parsed_payload,
            uploads=uploads,
            tenant_scope=tenant_scope,
            idempotency_key=idempotency_key,
        )
    except PublicWriteIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if settings.ENVIRONMENT != "test" and not replayed:
        background_tasks.add_task(
            RepairDiagnosticService.run_ai_pre_diagnosis,
            order_id=response.order_id,
            tenant_id=tenant_scope.tenant_id,
            payload_data=parsed_payload.model_dump(),
            nameplate_files=nameplate_files,
        )
    return response
