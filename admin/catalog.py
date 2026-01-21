import os
import uuid
import shutil
from sqladmin import ModelView, action, expose, BaseView
from sqladmin.fields import AjaxSelectMultipleField, QueryAjaxModelLoader
from markupsafe import Markup
from wtforms import TextAreaField, FileField
from sqlalchemy.orm import selectinload
from sqlmodel import select
import slugify

from models import Product, Tag, TagGroup, ProductTagLink
from core.database import async_session_maker
from starlette.responses import RedirectResponse
from .base import format_tags_shared
from services.image_service import ImageService


class ProductAdmin(ModelView, model=Product):
    name = "Товар"
    name_plural = "Товары"
    icon = "fa-solid fa-snowflake"
    
    list_template = "product_list.html"
    edit_template = "sqladmin/product_edit.html"
    
    # --- КОЛОНКИ ---
    column_list = ["id", "formatted_title", "price", "main_image", "formatted_area", "is_published"]
    column_searchable_list = ["title", "description"]
    column_default_sort = ("created_at", True)
    column_editable_list = ["is_published"]
    page_size = 100
    page_size_options = [25, 50, 100, 200]
    
    # --- ФОРМА: Порядок полей ---
    form_columns = [
        "title", "description", "price", "old_price", "area", "is_inverter", "power_cooling",
        "main_image", "images", 
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
        "specs": TextAreaField,
        "images": TextAreaField,
    }

    # --- Extra fields (только для файла, НЕ для tags!) ---
    form_extra_fields = {
        "main_image_file": FileField("Загрузить фото (изменит путь выше)"),
    }

    form_edit_rules = [
        "title", "description", "area", "is_inverter", "power_cooling", "price", "old_price", "source_url",
        "is_published", "main_image", "main_image_file", "images",
        "tags", "specs"
    ]
    form_create_rules = form_edit_rules
    
    # --- Eager loading для M2M + tag filtering ---
    def list_query(self, request):
        from sqlalchemy import func
        query = super().list_query(request)
        query = query.options(selectinload(Product.tags).selectinload(Tag.group))
        
        # Handle tag_ids filtering from URL
        tag_ids = request.query_params.getlist('tag_ids')
        if tag_ids:
            tag_ids = [int(tid) for tid in tag_ids]
            # AND logic: product must have ALL selected tags
            tag_subquery = (
                select(ProductTagLink.product_id)
                .where(ProductTagLink.tag_id.in_(tag_ids))
                .group_by(ProductTagLink.product_id)
                .having(func.count(ProductTagLink.tag_id) == len(tag_ids))
            )
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
            return Markup(f'<img src="{model.main_image}" style="height: 50px; border-radius: 5px;">')
        return ""

    def format_product_title(model, context):
        title_html = f'<strong>{model.title}</strong>'
        tags_html = format_tags_shared(model, context, hide_group=True)
        return Markup(f'{title_html}<br><div class="tags__product_title">{tags_html}</div>')

    def format_area(model, context):
        if model.area:
            return f"{model.area} м²"
        return "—"

    def format_price(model, context):
        if model.price:
            return f"{model.price:,}".replace(",", " ")
        return "—"

    column_formatters = {
        "main_image": format_image,
        "formatted_title": format_product_title,
        "formatted_area": format_area,
        "price": format_price
    }
    
    column_labels = {
        "formatted_title": "Товар",
        "formatted_area": "Площадь",
        "price": "Цена",
        "main_image": "Фото",
        "is_published": "Включён"
    }

    # --- Сохранение: обработка файла ---
    async def on_model_change(self, data, model, is_created, request):
        form = await request.form()
        upload = form.get("main_image_file")
        
        if "main_image_file" in data:
            del data["main_image_file"]

        if upload and hasattr(upload, "filename") and upload.filename:
            # Ensure slug exists
            if not data.get("slug") and data.get("title"):
                data["slug"] = slugify.slugify(data["title"])
            
            slug = data.get("slug") or model.slug or f"product-{uuid.uuid4().hex[:8]}"
            
            # Read file bytes
            file_bytes = await upload.read()
            
            # Use ImageService to save
            ext = upload.filename.split(".")[-1]
            filename = f"{uuid.uuid4()}.{ext}"
            
            db_path = ImageService.save_image(
                file_bytes=file_bytes,
                entity_type="products",
                slug=slug,
                filename=filename
            )
            
            # Store path with leading slash for web access
            data["main_image"] = ImageService.get_web_path(db_path)


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
    page_size = 50
    page_size_options = [25, 50, 100, 200]
    column_details_list = "__all__"

    form_columns = "__all__"
    
    column_formatters = {
        Tag.title: format_tags_shared
    }

    def list_query(self, request):
        query = super().list_query(request)
        return query.options(selectinload(self.model.group))


class BulkTagsView(BaseView):
    name = "Bulk Tags"
    icon = "fa-solid fa-tags"

    def is_visible(self, request):
        return False

    @expose("/bulk-tags", methods=["GET", "POST"])
    async def list(self, request):
        pks = request.query_params.get("pks", "").split(",")
        pks = [pk for pk in pks if pk]
        
        if request.method == "POST":
            form = await request.form()
            action_type = form.get("action_type")
            selected_tag_ids = form.getlist("tag_ids")
            
            async with async_session_maker() as session:
                stmt = select(Product).where(Product.id.in_(pks)).options(selectinload(Product.tags))
                res = await session.execute(stmt)
                products = res.scalars().all()
                
                t_stmt = select(Tag).where(Tag.id.in_(selected_tag_ids))
                t_res = await session.execute(t_stmt)
                tags_to_apply = t_res.scalars().all()
                
                for product in products:
                    if action_type == "add":
                        current_tag_ids = {t.id for t in product.tags}
                        for tag in tags_to_apply:
                            if tag.id not in current_tag_ids:
                                product.tags.append(tag)
                    elif action_type == "remove":
                        product.tags = [t for t in product.tags if str(t.id) not in selected_tag_ids]
                
                await session.commit()
            
            return RedirectResponse(
                url=f"{request.url_for('admin:list', identity='product')}?msg=Теги обновлены для {len(products)} товаров&type=success",
                status_code=303
            )

        async with async_session_maker() as session:
            g_stmt = select(TagGroup).options(selectinload(TagGroup.tags))
            g_res = await session.execute(g_stmt)
            groups = g_res.scalars().all()
            
            p_stmt = select(Product).where(Product.id.in_(pks))
            p_res = await session.execute(p_stmt)
            products = p_res.scalars().all()

        return await self.templates.TemplateResponse(
            request,
            "sqladmin/bulk_tags.html",
            {
                "model_view": self,
                "groups": groups,
                "products": products,
                "pks": pks,
            }
        )
