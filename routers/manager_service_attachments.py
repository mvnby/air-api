from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
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


async def _read_upload_limited(file: UploadFile) -> bytes:
    limit = int(settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES)
    content = bytearray()
    while True:
        chunk = await file.read(min(1024 * 1024, limit + 1))
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > limit:
            raise ValueError("Attachment exceeds the configured size limit")
    return bytes(content)


@router.get(
    "/orders/{order_id}/attachments",
    response_model=ManagerServiceAttachmentListResponse,
    operation_id=LIST_MANAGER_ORDER_ATTACHMENTS,
)
async def list_manager_order_attachments(
    order_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read active attachment links for a scoped order with their category, caption and
    equipment/service context. Missing or inaccessible order returns 404; no pagination
    parameters are accepted. This returns metadata rather than file bytes or permanent
    public URLs.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [private service
    attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
    """
    data = await ServiceAttachmentService.list_order_attachments(
        session,
        order_id=order_id,
        tenant_scope=tenant_scope,
    )
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read active private attachment links associated with customer equipment. Missing or
    inaccessible equipment returns 404; no pagination parameters are accepted. Attachment
    access remains subject to active link ownership; this does not publish files into the
    general media library.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [private service
    attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
    """
    data = await ServiceAttachmentService.list_equipment_attachments(
        session,
        equipment_id=equipment_id,
        tenant_scope=tenant_scope,
    )
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
    service_history_id: int | None = Form(None),
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Upload a private attachment and create its order link, optionally also linking validated
    work stage, equipment, component or service history. Empty/oversized files, unsupported
    type/category and invalid target relationships return 400. Image previews are generated
    during ingestion when supported; identical bytes may reuse storage while ordinary manual
    uploads still create separate attachment occurrences. No idempotency receipt is
    required.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [private service
    attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
    """
    try:
        content = await _read_upload_limited(file)
        return await ServiceAttachmentService.create_and_link_order_attachment(
            session,
            order_id=order_id,
            content=content,
            filename=file.filename or "attachment",
            mime_type=file.content_type,
            category=category,
            caption=caption,
            work_stage_id=work_stage_id,
            equipment_id=equipment_id,
            component_id=component_id,
            service_history_id=service_history_id,
            created_by=username,
            tenant_scope=tenant_scope,
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Update attachment/link metadata without replacing its file bytes. order_id is required
    to change category, caption or equipment/component/history association; missing context
    or invalid relationships returns 400. Missing/archived or inaccessible attachment
    returns 404. Shared metadata changes require all active links to be owned by the
    caller’s scope; per-order link edits update the corresponding equipment context.

    Access and scope: Manager access is required; active attachment links must pass order
    tenant/storefront or equipment customer-tenant ownership checks. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [private service
    attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
    """
    try:
        data = await ServiceAttachmentService.update_attachment(
            session,
            attachment_id=attachment_id,
            order_id=payload.order_id,
            payload=payload.model_dump(exclude_unset=True, exclude={"order_id"}),
            tenant_scope=tenant_scope,
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Archive an attachment’s link to the specified order and its derived equipment links,
    returning 204. Without order_id all active links must be owned by the caller before
    archival; the attachment is archived only when no active links remain. File bytes are
    retained. Missing/inaccessible/already archived attachment or link returns 404,
    including repeats.

    Access and scope: Manager access is required; active attachment links must pass order
    tenant/storefront or equipment customer-tenant ownership checks. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [private service
    attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
    """
    if not await ServiceAttachmentService.archive_attachment(
        session,
        attachment_id=attachment_id,
        order_id=order_id,
        tenant_scope=tenant_scope,
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Issue a short-lived access URL for an active private attachment after ownership checks,
    optionally for download. Requested preview falls back to original when no preview
    exists; the returned variant identifies the actual file. URL expiry is configured
    between 30 and 3600 seconds. Missing/inaccessible attachment or source returns 404. The
    returned URL grants temporary file access; this does not create a permanent public media
    URL.

    Access and scope: Manager access is required; active attachment links must pass order
    tenant/storefront or equipment customer-tenant ownership checks. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [private service
    attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
    """
    try:
        data = await ServiceAttachmentService.get_access(
            session,
            attachment_id=attachment_id,
            variant=variant,
            download=download,
            tenant_scope=tenant_scope,
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
