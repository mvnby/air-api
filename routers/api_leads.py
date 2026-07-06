"""Public website lead capture endpoints."""

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from schemas import ProductAvailabilityLeadPayload, ProductAvailabilityLeadResponse
from services.repair_diagnostic_service import (
    RepairDiagnosticLeadResponse,
    RepairDiagnosticService,
)
from services.website_lead_service import WebsiteLeadService

router = APIRouter(tags=["api"])


@router.post(
    "/v1/leads/product-availability",
    response_model=ProductAvailabilityLeadResponse,
    operation_id="create_product_availability_lead",
)
async def create_product_availability_lead(
    payload: ProductAvailabilityLeadPayload,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await WebsiteLeadService.create_product_availability_lead(session, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/v1/leads/repair-diagnostic",
    response_model=RepairDiagnosticLeadResponse,
    operation_id="create_repair_diagnostic_lead",
)
async def create_repair_diagnostic_lead(
    background_tasks: BackgroundTasks,
    payload: str = Form(...),
    nameplate: Optional[List[UploadFile]] = File(default=None),
    indoor_unit: Optional[List[UploadFile]] = File(default=None),
    outdoor_unit: Optional[List[UploadFile]] = File(default=None),
    error_display: Optional[List[UploadFile]] = File(default=None),
    leak_place: Optional[List[UploadFile]] = File(default=None),
    session: AsyncSession = Depends(get_session),
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
        response, nameplate_files = await RepairDiagnosticService.create_lead(
            session,
            payload=parsed_payload,
            uploads=uploads,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if settings.ENVIRONMENT != "test":
        background_tasks.add_task(
            RepairDiagnosticService.run_ai_pre_diagnosis,
            order_id=response.order_id,
            payload_data=parsed_payload.model_dump(),
            nameplate_files=nameplate_files,
        )
    return response
