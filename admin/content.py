import os
import shutil
import uuid
from typing import Any
from sqladmin import ModelView
from wtforms import FileField, TextAreaField
from slugify import slugify
from markupsafe import Markup

from models import Article
from services.image_service import ImageService

class ArticleAdmin(ModelView, model=Article):
    name = "Статья"
    name_plural = "Статьи"
    icon = "fa-solid fa-newspaper"
    
    column_list = [
        "id", "main_image", "title", "is_published", "created_at"
    ]
    
    column_labels = {
        "main_image": "Превью",
        "title": "Заголовок",
        "is_published": "Опубл.",
        "created_at": "Создана"
    }

    form_extra_fields = {
        "main_image_file": FileField("Загрузить обложку")
    }
    
    form_columns = [
        "title", "slug", "content", "is_published"
    ]

    form_create_rules = [
        "title", "slug", "main_image_file", "content", "is_published"
    ]
    form_edit_rules = form_create_rules

    form_overrides = {
        "content": TextAreaField
    }

    async def scaffold_form(self, rules=None, **kwargs):
        # We call super() WITHOUT rules to avoid KeyError for extra fields
        # sqladmin will use form_columns by default.
        form_class = await super().scaffold_form()
        form_class.main_image_file = self.form_extra_fields["main_image_file"]
        return form_class

    create_template = "sqladmin/article_create.html"
    edit_template = "sqladmin/article_edit.html"

    column_formatters = {
        "main_image": lambda m, c: Markup(f'<img src="{m.main_image}" width="50">') if m.main_image else ""
    }

    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Any) -> None:
        # 1. Handle Slug
        if not data.get("slug"):
            data["slug"] = slugify(data.get("title", "article"))

        # 2. Handle Image Upload
        upload_field = data.get("main_image_file")
        if upload_field and hasattr(upload_field, 'filename') and upload_field.filename:
            slug = data.get("slug") or model.slug or f"article-{uuid.uuid4().hex[:8]}"
            
            # Read file bytes
            file_bytes = await upload_field.read()
            
            # Use ImageService to save
            ext = upload_field.filename.split(".")[-1]
            filename = f"{slugify(slug)}_{upload_field.filename}"
            
            db_path = ImageService.save_image(
                file_bytes=file_bytes,
                entity_type="articles",
                slug=slug,
                filename=filename
            )
            
            # Set the URL in the NEW cover_image field
            data["cover_image"] = ImageService.get_web_path(db_path)
        
        # Security: Remove the temporary file field so it doesn't break SQLModel
        if "main_image_file" in data:
            del data["main_image_file"]
