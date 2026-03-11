from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import DOCUMENT_NOT_FOUND, BAD_REQUEST
from core.security import get_current_username
from routers.manager_operation_ids import (
    GET_MANAGER_ORDER_DOCUMENTS,
    UPLOAD_MANAGER_ORDER_DOCUMENT,
    GET_MANAGER_DOC_DOWNLOAD,
    DELETE_MANAGER_DOC,
)
from schemas import (
    ManagerOrderDocumentListResponse,
    ManagerOrderDocumentItem,
    ManagerActionMessageResponse,
)
from services.document_service import DocumentService


router = APIRouter(prefix="/api/manager", tags=["manager-docs"])


@router.get(
    "/orders/{order_id}/documents",
    response_model=ManagerOrderDocumentListResponse,
    operation_id=GET_MANAGER_ORDER_DOCUMENTS,
)
async def get_manager_order_documents(
    order_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    docs = await DocumentService.list_order_documents(session, order_id)
    return {
        "items": [
            ManagerOrderDocumentItem(
                id=d.id,
                doc_type=d.doc_type,
                number=d.number,
                date=d.date,
                edit_url=d.google_edit_url,
            )
            for d in docs
        ]
    }


@router.post(
    "/orders/{order_id}/documents/upload",
    response_model=ManagerOrderDocumentItem,
    operation_id=UPLOAD_MANAGER_ORDER_DOCUMENT,
)
async def upload_manager_order_document(
    order_id: int,
    file: UploadFile = File(...),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    doc = await DocumentService.upload_document(session, order_id, file)
    return ManagerOrderDocumentItem(
        id=doc.id,
        doc_type=doc.doc_type,
        number=doc.number,
        date=doc.date,
        edit_url=doc.google_edit_url,
    )


@router.get(
    "/docs/{doc_id}/download",
    operation_id=GET_MANAGER_DOC_DOWNLOAD,
)
async def get_manager_doc_download(
    doc_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        pdf_content, filename_encoded = await DocumentService.get_download_stream(session, doc_id)
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=GET_MANAGER_DOC_DOWNLOAD,
            error_code=BAD_REQUEST,
            message=str(exc),
        )

    if not pdf_content:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_DOC_DOWNLOAD,
            error_code=DOCUMENT_NOT_FOUND,
        )

    return StreamingResponse(
        pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}"
        },
    )


@router.delete(
    "/docs/{doc_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_DOC,
)
async def delete_manager_doc(
    doc_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    order_id = await DocumentService.delete_document(session, doc_id)
    
    if not order_id:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_MANAGER_DOC,
            error_code=DOCUMENT_NOT_FOUND,
        )

    return {"message": "Document deleted"}
