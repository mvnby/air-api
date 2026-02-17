from sqladmin import ModelView
from markupsafe import Markup
from wtforms import TextAreaField, FileField
from wtforms.validators import DataRequired
from sqlalchemy.orm import selectinload
from sqlmodel import select
import slugify

from models import Product, Tag, TagGroup, ProductTagLink
from .catalog_constants import (
    GALLERY_STATUS_EMPTY_BADGE,
    GALLERY_STATUS_PRESENT_TEMPLATE,
    PAGE_SIZE_OPTIONS,
    PRODUCT_ADMIN_PAGE_SIZE,
    PRODUCT_AREA_SUFFIX,
    PRODUCT_EMPTY_PLACEHOLDER,
    PRODUCT_IMAGES_READONLY_DESCRIPTION,
    PRODUCT_IMAGE_PREVIEW_STYLE,
    PRODUCT_MAIN_IMAGE_UPLOAD_LABEL,
    PRODUCT_SLUG_DESCRIPTION,
    PRODUCT_SLUG_LABEL,
    TAG_ADMIN_PAGE_SIZE,
)
from .formatters import format_tags_shared
from services.product_service import ProductService


class ProductAdmin(ModelView, model=Product):
    name = "Товар"
    name_plural = "Товары"
    icon = "fa-solid fa-snowflake"
    
    list_template = "product_list.html"
    edit_template = "sqladmin/product_edit.html"
    
    # --- КОЛОНКИ ---
    column_list = ["id", "formatted_title", "price", "main_image", "gallery_status", "formatted_area", "is_published"]
    column_searchable_list = ["title", "description"]
    column_default_sort = ("created_at", True)
    column_editable_list = ["is_published"]
    page_size = PRODUCT_ADMIN_PAGE_SIZE
    page_size_options = PAGE_SIZE_OPTIONS
    
    # --- ФОРМА: Порядок полей ---
    form_columns = [
        "title", "slug", "description", "price", "old_price", "area", "is_inverter", "power_cooling",
        "main_image", 
        "images", # Legacy field (Read-Only)
        "tags",  # M2M handled by form_ajax_refs
        "specs", "is_published", "source_url"
    ]

    # --- AJAX для M2M: SQLAdmin сам создаст Select2 виджет ---
    form_ajax_refs = {
        "tags": {
            "fields": ["title", "slug"],
            "order_by": "title",
            "placeholder": "Начните вводить характеристику...",
            "minimum_input_length": 0,
        }
    }
    
    # --- Оверрайды для НЕ-relationship полей ---
    form_overrides = {
        "description": TextAreaField,
        "images": TextAreaField,
        # "slug" removed from overrides
    }
    
    # --- Extra fields (только для файла!) ---
    form_extra_fields = {
        "main_image_file": FileField(PRODUCT_MAIN_IMAGE_UPLOAD_LABEL),
    }

    form_edit_rules = [
        "title", "slug", "description", "area", "is_inverter", "power_cooling", "price", "old_price", "source_url",
        "is_published", "main_image", "main_image_file", "images",
        "tags", "specs"
    ]
    form_create_rules = form_edit_rules
    
    # --- Eager loading для M2M + tag filtering ---
    @staticmethod
    def _parse_tag_ids(request) -> list[int]:
        raw_ids = request.query_params.getlist("tag_ids")
        if not raw_ids:
            return []
        return [int(tag_id) for tag_id in raw_ids]

    @staticmethod
    def _build_tag_filter_subquery(tag_ids: list[int]):
        from sqlalchemy import func

        return (
            select(ProductTagLink.product_id)
            .where(ProductTagLink.tag_id.in_(tag_ids))
            .group_by(ProductTagLink.product_id)
            .having(func.count(ProductTagLink.tag_id) == len(tag_ids))
        )

    def list_query(self, request):
        query = super().list_query(request)
        query = query.options(
            selectinload(Product.tags).selectinload(Tag.group),
            selectinload(Product.gallery_images)
        )

        tag_ids = self._parse_tag_ids(request)
        if tag_ids:
            # AND logic: product must have ALL selected tags
            tag_subquery = self._build_tag_filter_subquery(tag_ids)
            query = query.where(Product.id.in_(tag_subquery))

        return query
    
    def detail_query(self, request):
        query = super().detail_query(request)
        return query.options(selectinload(Product.tags).selectinload(Tag.group))

    def edit_query(self, request):
        query = super().edit_query(request)
        return query.options(selectinload(Product.tags).selectinload(Tag.group))

    # --- Scaffold form: добавляем только file field ---
    async def scaffold_form(self, *args, **kwargs):
        form_class = await super().scaffold_form(*args, **kwargs)
        form_class.main_image_file = self.form_extra_fields["main_image_file"]
        return form_class


    # --- Formatters ---
    def format_image(model, context):
        if model.main_image:
            url = model.main_image if model.main_image.startswith("/") else f"/{model.main_image}"
            return Markup(f'<img src="{url}" style="{PRODUCT_IMAGE_PREVIEW_STYLE}">')
        return ""

    def format_product_title(model, context):
        title_html = f'<strong>{model.title}</strong>'
        tags_html = format_tags_shared(model, context, hide_group=True)
        return Markup(f'{title_html}<br><div class="tags__product_title">{tags_html}</div>')

    def format_area(model, context):
        if model.area:
            return f"{model.area}{PRODUCT_AREA_SUFFIX}"
        return PRODUCT_EMPTY_PLACEHOLDER

    def format_price(model, context):
        if model.price:
            return f"{model.price:,}".replace(",", " ")
        return PRODUCT_EMPTY_PLACEHOLDER

    def format_gallery_status(model, context):
        if model.gallery_images:
            return Markup(GALLERY_STATUS_PRESENT_TEMPLATE.format(count=len(model.gallery_images)))
        return Markup(GALLERY_STATUS_EMPTY_BADGE)

    column_formatters = {
        "main_image": format_image,
        "formatted_title": format_product_title,
        "formatted_area": format_area,
        "price": format_price,
        "gallery_status": format_gallery_status,
    }
    
    column_labels = {
        "formatted_title": "Товар",
        "formatted_area": "Площадь",
        "price": "Цена",
        "main_image": "Фото",
        "gallery_status": "Галерея",
        "is_published": "Включён"
    }
    
    # Make legacy images field read-only
    form_args = {
        "slug": {
            "validators": [DataRequired()],
            "label": PRODUCT_SLUG_LABEL,
            "description": PRODUCT_SLUG_DESCRIPTION,
        },
        "images": {
            "render_kw": {"readonly": True, "style": "background-color: #f8f9fa;"},
            "description": PRODUCT_IMAGES_READONLY_DESCRIPTION,
        },
    }

    def _ensure_slug(self, data: dict) -> None:
        if not data.get("slug") and data.get("title"):
            data["slug"] = slugify.slugify(data["title"])

    @staticmethod
    def _extract_uploaded_main_image(form):
        upload = form.get("main_image_file")
        if upload and hasattr(upload, "filename") and upload.filename:
            return upload
        return None

    async def _save_new_product_main_image(self, model, upload) -> None:
        file_bytes = await upload.read()
        async with async_session_maker() as session:
            await ProductService.save_main_image(
                session=session,
                product_id=model.id,
                file_bytes=file_bytes,
                filename=upload.filename,
            )

    async def _set_existing_product_main_image(self, data: dict, model, upload) -> None:
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

    # --- Сохранение: обработка файла через ProductService ---
    async def on_model_change(self, data, model, is_created, request):
        form = await request.form()
        upload = self._extract_uploaded_main_image(form)
        data.pop("main_image_file", None)
        self._ensure_slug(data)

        if not upload:
            await super().on_model_change(data, model, is_created, request)
            return

        if is_created:
            await super().on_model_change(data, model, is_created, request)
            await self._save_new_product_main_image(model, upload)
            return

        await self._set_existing_product_main_image(data, model, upload)
        await super().on_model_change(data, model, is_created, request)


class TagGroupAdmin(ModelView, model=TagGroup):
    name = "Группа тегов"
    name_plural = "Группы тегов"
    icon = "fa-solid fa-layer-group"
    column_list = [TagGroup.id, TagGroup.title, TagGroup.slug, TagGroup.is_public, TagGroup.color]
    column_labels = {
        "id": "ID",
        "title": "Название",
        "slug": "Slug",
        "is_public": "Публичная",
        "color": "Цвет"
    }
    column_details_list = "__all__"
    form_columns = "__all__"


class TagAdmin(ModelView, model=Tag):
    name = "Тег"
    name_plural = "Теги"
    icon = "fa-solid fa-tag"
    column_list = [Tag.id, Tag.title, Tag.is_public, Tag.is_filter]
    column_labels = {
        "id": "ID",
        "title": "Название",
        "is_public": "Публичный",
        "is_filter": "Фильтр"
    }
    page_size = TAG_ADMIN_PAGE_SIZE
    page_size_options = PAGE_SIZE_OPTIONS
    column_details_list = "__all__"

    form_columns = "__all__"
    
    column_formatters = {
        Tag.title: format_tags_shared
    }

    def list_query(self, request):
        query = super().list_query(request)
        return query.options(selectinload(self.model.group))

