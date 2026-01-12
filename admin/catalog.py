import os
import uuid
import shutil
from sqladmin import ModelView, action, expose, BaseView
from markupsafe import Markup
from wtforms import TextAreaField, FileField
from sqlalchemy.orm import selectinload
from sqlmodel import select
import slugify

from models import Product, Tag, TagGroup
from forms import TagListField
from database import async_session_maker
from starlette.responses import RedirectResponse
from .base import format_tags_shared

class ProductAdmin(ModelView, model=Product):
    """Настройки отображения товаров в админке"""
    name = "Товар"
    name_plural = "Товары"
    icon = "fa-solid fa-snowflake"
    
    list_template = "product_list.html"
    edit_template = "sqladmin/product_edit.html"
    column_list = ["id", "formatted_title", "price", "main_image", "formatted_area", "is_published"]
    column_searchable_list = ["title", "description"]
    # column_filters = [Product.is_inverter, Product.area, Product.is_published]
    column_default_sort = ("created_at", True)
    column_editable_list = ["is_published"]
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
        "title", "description", "price", "old_price", "area", "is_inverter", "power_cooling",
        "main_image", "images", "tags", "specs", "is_published", "source_url"
    ]
    
    form_edit_rules = [
        "title", "description", "area", "is_inverter", "power_cooling", "price", "old_price", "source_url",
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
            action_type = form.get("action_type") # add/remove
            selected_tag_ids = form.getlist("tag_ids")
            
            async with async_session_maker() as session:
                # Fetch products
                stmt = select(Product).where(Product.id.in_(pks)).options(selectinload(Product.tags))
                res = await session.execute(stmt)
                products = res.scalars().all()
                
                # Fetch tags
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
            
            # Redirect back to Product List
            return RedirectResponse(
                url=f"{request.url_for('admin:list', identity='product')}?msg=Теги обновлены для {len(products)} товаров&type=success",
                status_code=303
            )

        # GET: show form
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
