from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    DELETE_MANAGER_SERVICE_ATTACHMENT,
    GET_MANAGER_SERVICE_ATTACHMENT_ACCESS,
    LIST_MANAGER_EQUIPMENT_ATTACHMENTS,
    LIST_MANAGER_ORDER_ATTACHMENTS,
    PATCH_MANAGER_SERVICE_ATTACHMENT,
    UPLOAD_MANAGER_ORDER_ATTACHMENT,
)
from schemas import (
    ManagerServiceAttachmentAccessResponse,
    ManagerServiceAttachmentItemResponse,
    ManagerServiceAttachmentListResponse,
    ManagerServiceAttachmentUpdatePayload,
)
from services.service_attachment_service import ServiceAttachmentService


router = APIRouter(prefix="/api/manager", tags=["manager-service-attachments"])


@router.get(
    "/orders/{order_id}/attachments",
    response_model=ManagerServiceAttachmentListResponse,
    operation_id=LIST_MANAGER_ORDER_ATTACHMENTS,
)
async def list_manager_order_attachments(
    order_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    data = await ServiceAttachmentService.list_order_attachments(session, order_id=order_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return data


@router.get(
    "/equipment/{equipment_id}/attachments",
    response_model=ManagerServiceAttachmentListResponse,
    operation_id=LIST_MANAGER_EQUIPMENT_ATTACHMENTS,
)
async def list_manager_equipment_attachments(
    equipment_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    data = await ServiceAttachmentService.list_equipment_attachments(session, equipment_id=equipment_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return data


@router.post(
    "/orders/{order_id}/attachments",
    response_model=ManagerServiceAttachmentItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=UPLOAD_MANAGER_ORDER_ATTACHMENT,
)
async def upload_manager_order_attachment(
    order_id: int,
    file: UploadFile = File(...),
    category: str = Form("other"),
    caption: str | None = Form(None),
    work_stage_id: int | None = Form(None),
    equipment_id: int | None = Form(None),
    component_id: int | None = Form(None),
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await ServiceAttachmentService.create_and_link_order_attachment(
            session,
            order_id=order_id,
            content=await file.read(),
            filename=file.filename or "attachment",
            mime_type=file.content_type,
            category=category,
            caption=caption,
            work_stage_id=work_stage_id,
            equipment_id=equipment_id,
            component_id=component_id,
            created_by=username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/service-attachments/{attachment_id}",
    response_model=ManagerServiceAttachmentItemResponse,
    operation_id=PATCH_MANAGER_SERVICE_ATTACHMENT,
)
async def patch_manager_service_attachment(
    attachment_id: int,
    payload: ManagerServiceAttachmentUpdatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await ServiceAttachmentService.update_attachment(
            session,
            attachment_id=attachment_id,
            order_id=payload.order_id,
            payload=payload.model_dump(exclude_unset=True, exclude={"order_id"}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return data


@router.delete(
    "/service-attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id=DELETE_MANAGER_SERVICE_ATTACHMENT,
)
async def delete_manager_service_attachment(
    attachment_id: int,
    order_id: int | None = Query(None),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    if not await ServiceAttachmentService.archive_attachment(
        session,
        attachment_id=attachment_id,
        order_id=order_id,
    ):
        raise HTTPException(status_code=404, detail="Attachment not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/service-attachments/{attachment_id}/access",
    response_model=ManagerServiceAttachmentAccessResponse,
    operation_id=GET_MANAGER_SERVICE_ATTACHMENT_ACCESS,
)
async def get_manager_service_attachment_access(
    attachment_id: int,
    variant: str = Query("original", pattern="^(original|preview)$"),
    download: bool = Query(False),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await ServiceAttachmentService.get_access(
            session,
            attachment_id=attachment_id,
            variant=variant,
            download=download,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return data


@router.get(
    "/service-attachments/{attachment_id}/content",
    include_in_schema=False,
)
async def read_manager_service_attachment_content(
    attachment_id: int,
    variant: str = Query("original", pattern="^(original|preview)$"),
    expires: int = Query(...),
    download: bool = Query(False),
    signature: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    if not ServiceAttachmentService.validate_local_signature(
        attachment_id=attachment_id,
        variant=variant,
        expires=expires,
        download=download,
        signature=signature,
    ):
        raise HTTPException(status_code=403, detail="Attachment link expired or invalid")
    try:
        attachment, content, mime_type = await ServiceAttachmentService.read_variant(
            session,
            attachment_id=attachment_id,
            variant=variant,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if download:
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(attachment.original_filename)}"
    return Response(content=content, media_type=mime_type, headers=headers)
