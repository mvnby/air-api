import os
import shutil
from typing import Any
from sqladmin import ModelView
from wtforms import FileField, TextAreaField
from slugify import slugify
from markupsafe import Markup

from models import Article

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
            # Create uploads dir if not exists
            upload_dir = "/Users/maksimkorotov/dev/mvn/static/uploads/articles"
            os.makedirs(upload_dir, exist_ok=True)
            
            filename = f"{slugify(data['slug'])}_{upload_field.filename}"
            file_path = os.path.join(upload_dir, filename)
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(upload_field.file, buffer)
            
            # Set the URL in the database field
            data["main_image"] = f"/static/uploads/articles/{filename}"
        
        # Security: Remove the temporary file field so it doesn't break SQLModel
        if "main_image_file" in data:
            del data["main_image_file"]
