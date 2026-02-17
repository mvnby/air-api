import slugify
from sqlmodel import select

from core.database import async_session_maker
from models import Product, ProductTagLink
from services.product_service import ProductService


def parse_tag_ids(request) -> list[int]:
    raw_ids = request.query_params.getlist("tag_ids")
    if not raw_ids:
        return []
    return [int(tag_id) for tag_id in raw_ids]


def build_tag_filter_subquery(tag_ids: list[int]):
    from sqlalchemy import func

    return (
        select(ProductTagLink.product_id)
        .where(ProductTagLink.tag_id.in_(tag_ids))
        .group_by(ProductTagLink.product_id)
        .having(func.count(ProductTagLink.tag_id) == len(tag_ids))
    )


def ensure_slug(data: dict) -> None:
    if not data.get("slug") and data.get("title"):
        data["slug"] = slugify.slugify(data["title"])


def extract_uploaded_main_image(form):
    upload = form.get("main_image_file")
    if upload and hasattr(upload, "filename") and upload.filename:
        return upload
    return None


async def save_new_product_main_image(model, upload) -> None:
    file_bytes = await upload.read()
    async with async_session_maker() as session:
        await ProductService.save_main_image(
            session=session,
            product_id=model.id,
            file_bytes=file_bytes,
            filename=upload.filename,
        )


async def set_existing_product_main_image(data: dict, model, upload) -> None:
    from services.image_service import ImageService

    file_bytes = await upload.read()
    async with async_session_maker() as session:
        stmt = select(Product).where(Product.id == model.id)
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()

        if not product:
            return

        db_path = await ImageService.save_image(
            file_bytes=file_bytes,
            entity_type="products",
            slug=product.slug,
            filename=upload.filename,
        )
        data["main_image"] = ImageService.get_web_path(db_path)
