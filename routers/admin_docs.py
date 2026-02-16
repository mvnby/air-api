from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlmodel import select

from core.database import async_session_maker
from core.security import get_current_username
from services.document_service import DocumentService


router = APIRouter(tags=["admin-docs"])


@router.get("/docs/generate/{doc_type}/{order_id}")
async def generate_document(
    doc_type: str,
    order_id: int,
    username: str = Depends(get_current_username)
):
    """
    Универсальный роут для генерации документов.
    doc_type: contract | offer | invoice | act | tn2 | ttn1
    Возвращает ссылку на редактирование в Google Docs.
    """
    async with async_session_maker() as session:
        try:
            doc = await DocumentService.create_or_get_document(session, order_id, doc_type)
            return RedirectResponse(url=doc.google_edit_url)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return {"error": str(exc)}


@router.get("/docs/download/{doc_id}")
async def download_document_pdf(
    doc_id: int,
    username: str = Depends(get_current_username)
):
    """
    Скачивает документ в формате PDF из Google Drive.
    """
    from models import OrderDocument
    from services.google_service import google_service

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrderDocument).where(OrderDocument.id == doc_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        try:
            pdf_content = google_service.export_file(document.google_file_id, mime_type='application/pdf')

            from urllib.parse import quote
            filename = f"{document.number}.pdf"
            filename_encoded = quote(filename)

            return StreamingResponse(
                pdf_content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}"
                }
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Error exporting PDF: {str(exc)}")


@router.get("/docs/delete/{doc_id}")
async def delete_document(
    doc_id: int,
    username: str = Depends(get_current_username)
):
    """
    Удаляет документ из БД и перемещает файл в корзину Google Drive.
    """
    from models import OrderDocument
    from services.google_service import google_service

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrderDocument).where(OrderDocument.id == doc_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        order_id = document.order_id

        if document.google_file_id:
            try:
                google_service.delete_file(document.google_file_id)
            except Exception as exc:
                print(f"Error deleting file from Drive: {exc}")

        await session.delete(document)
        await session.commit()

        return RedirectResponse(
            url=f"/admin/order/edit/{order_id}",
            status_code=302
        )
