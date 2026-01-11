import os
import uuid
import shutil
from typing import Any
from sqladmin import ModelView
from markupsafe import Markup
from wtforms import TextAreaField, FileField
from sqlalchemy.orm import selectinload
from sqlmodel import select
import slugify

from models import Product, Article, Tag, TagGroup, Order
from forms import TagListField
from database import async_session_maker
from core.config import settings

def format_tags_shared(model, context, hide_group: bool = False):
    """Shared formatter for Tag badges"""
    html = ""
    # Support both direct tag list and models with .tags
    tags = model.tags if hasattr(model, "tags") else []
    if not tags and isinstance(model, Tag):
        tags = [model]
        
    for tag in tags:
        color = "secondary"
        if tag.group:
            color = tag.group.color
        
        # If tag is not public, use an outlined/muted style
        opacity = "1" if tag.is_public else "0.5"
        border = "1px solid #ccc" if not tag.is_public else "none"
        
        # Include group name in small text if available, unless hidden
        group_prefix = ""
        if not hide_group and tag.group:
            group_prefix = f'<small style="opacity: 0.7;">{tag.group.title}:</small> '
        
        html += f'<span class="badge bg-{color}" style="margin-right: 5px; opacity: {opacity}; border: {border};">{group_prefix}{tag.title}</span>'
    return Markup(html)

class ProductAdmin(ModelView, model=Product):
    """Настройки отображения товаров в админке"""
    name = "Товар"
    name_plural = "Товары"
    icon = "fa-solid fa-snowflake"
    
    list_template = "product_list.html"
    column_list = ["id", "formatted_title", "price", "main_image", "formatted_area", "is_published"]
    column_searchable_list = ["title", "description"]
    column_default_sort = ("created_at", True)
    column_editable_list = ["price", "old_price", "is_published"]
    page_size = 100
    page_size_options = [25, 50, 100, 200]
    export_types = ["csv", "json"]
    
    def list_query(self, request):
        query = super().list_query(request)
        return query.options(selectinload(self.model.tags).selectinload(Tag.group))

    def detail_query(self, request):
        query = super().detail_query(request)
        return query.options(selectinload(self.model.tags).selectinload(Tag.group))

    def edit_query(self, request):
        query = super().edit_query(request)
        return query.options(selectinload(self.model.tags).selectinload(Tag.group))
    
    # --- Formatters ---
    def format_image(model, context):
        if model.main_image:
            return Markup(f'<img src="{model.main_image}" style="height: 50px; border-radius: 5px;">')
        return ""

    def format_product_title(model, context):
        title_html = f'<strong>{model.title}</strong>'
        tags_html = format_tags_shared(model, context, hide_group=True)
        return Markup(f'{title_html}<br><div style="margin-top: 5px;">{tags_html}</div>')

    def format_area(model, context):
        if model.area:
            return f"{model.area} м²"
        return "—"

    column_formatters = {
        "main_image": format_image,
        "formatted_title": format_product_title,
        "formatted_area": format_area
    }
    
    column_labels = {
        "formatted_title": "Товар",
        "formatted_area": "Площа"
    }
    
    form_overrides = {
        "tags": TagListField,
        "description": TextAreaField,
        "specs": TextAreaField,
        "images": TextAreaField,
    }
    
    form_extra_fields = {
        "main_image_file": FileField("Загрузить фото (изменит путь выше)")
    }
    
    form_columns = [
        "title", "description", "price", "old_price", "area", 
        "main_image", "images", "tags", "specs", "is_published", "source_url"
    ]
    
    form_edit_rules = [
        "title", "description", "area", "price", "old_price", "source_url",
        "is_published", "main_image", "main_image_file", "images",
        "tags", "specs"
    ]
    form_create_rules = form_edit_rules

    async def scaffold_form(self, *args, **kwargs):
        form_class = await super().scaffold_form(*args, **kwargs)
        form_class.main_image_file = self.form_extra_fields["main_image_file"]
        return form_class
    
    async def on_model_change(self, data, model, is_created, request):
        if "tags" in data:
            model._temp_tag_names = data["tags"]
            del data["tags"]
            
        form = await request.form()
        upload = form.get("main_image_file")
        
        if "main_image_file" in data:
            del data["main_image_file"]

        if upload and hasattr(upload, "filename") and upload.filename:
            ext = upload.filename.split(".")[-1]
            filename = f"{uuid.uuid4()}.{ext}"
            upload_dir = os.path.join("static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            data["main_image"] = f"/static/uploads/{filename}"

    async def after_model_change(self, data, model, is_created, request):
        if hasattr(model, "_temp_tag_names"):
            tag_names = model._temp_tag_names
            delattr(model, "_temp_tag_names") 
            
            try:
                async with async_session_maker() as session:
                    stmt = select(Product).where(Product.id == model.id).options(selectinload(Product.tags))
                    result = await session.execute(stmt)
                    db_product = result.scalar_one()
                    
                    new_tags = []
                    for name in tag_names:
                        name = name.strip()
                        if not name: continue
                        
                        c_stmt = select(Tag).where(Tag.title == name)
                        c_res = await session.execute(c_stmt)
                        tag = c_res.scalar_one_or_none()
                        
                        if not tag:
                            slug = slugify.slugify(name)
                            tag = Tag(title=name, slug=slug, is_public=True)
                            session.add(tag) 
                        
                        new_tags.append(tag)
                    
                    db_product.tags = new_tags
                    await session.commit()
            except Exception as e:
                print(f"ERROR in after_model_change: {e}")

class ArticleAdmin(ModelView, model=Article):
    name = "Статья"
    name_plural = "Статьи"
    icon = "fa-solid fa-newspaper"
    column_list = [Article.title, Article.created_at]

class TagGroupAdmin(ModelView, model=TagGroup):
    name = "Группа тегов"
    name_plural = "Группы тегов"
    icon = "fa-solid fa-layer-group"
    column_list = [TagGroup.id, TagGroup.title, TagGroup.slug, TagGroup.is_public, TagGroup.color]
    column_details_list = "__all__"
    form_columns = "__all__"

class TagAdmin(ModelView, model=Tag):
    name = "Тег"
    name_plural = "Теги"
    icon = "fa-solid fa-tag"
    column_list = [Tag.id, Tag.title, Tag.is_public, Tag.is_filter]
    column_details_list = "__all__"
    form_columns = "__all__"
    
    column_formatters = {
        Tag.title: format_tags_shared
    }

    def list_query(self, request):
        query = super().list_query(request)
        return query.options(selectinload(self.model.group))

class OrderAdmin(ModelView, model=Order):
    name = "Заказ"
    name_plural = "Заказы"
    icon = "fa-solid fa-cart-shopping"
    column_list = [Order.id, Order.status, Order.product, Order.user_id, Order.phone, Order.created_at]
    column_sortable_list = [Order.id, Order.created_at, Order.status]
    column_default_sort = ("created_at", True)
    column_editable_list = ["status"]
    
    def list_query(self, request):
        query = super().list_query(request)
        return query.options(selectinload(self.model.product))

    def detail_query(self, request):
        query = super().detail_query(request)
        return query.options(selectinload(self.model.product))
