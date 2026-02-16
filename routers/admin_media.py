from typing import List, Optional

from fastapi import APIRouter, Depends, Form, UploadFile

from core.security import get_current_username


router = APIRouter(tags=["admin-media"])


@router.post("/api/upload_images")
async def upload_images(
    files: List[UploadFile],
    slug: Optional[str] = Form(None),
    username: str = Depends(get_current_username)
):
    """
    Bulk upload images for articles/products.
    Returns list of web-accessible URLs.
    """
    from services.image_service import ImageService

    uploaded_urls = []
    effective_slug = slug or "uploads"
    entity_type = "articles"

    for file in files:
        file_bytes = await file.read()
        filename = file.filename or "image.jpg"

        db_path = await ImageService.save_image(
            file_bytes=file_bytes,
            entity_type=entity_type,
            slug=effective_slug,
            filename=filename
        )

        web_path = ImageService.get_web_path(db_path)
        uploaded_urls.append(web_path)

    return {"urls": uploaded_urls}


@router.get("/api/article_images/{slug}")
async def list_article_images(
    slug: str,
    username: str = Depends(get_current_username)
):
    """
    List all images associated with an article slug.
    """
    from services.image_service import ImageService

    urls = await ImageService.list_images("articles", slug)
    return {"urls": urls}
