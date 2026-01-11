import os
import shutil
from typing import Any
from sqladmin import ModelView
from wtforms import FileField
from slugify import slugify
from markupsafe import Markup

from models import Article

class ArticleAdmin(ModelView, model=Article):
    name = "Статья"
    name_plural = "Статьи"
    icon = "fa-solid fa-newspaper"
    
    column_list = [
        Article.id,
        Article.main_image,
        Article.title, 
        Article.is_published,
        Article.created_at
    ]
    
    column_labels = {
        Article.main_image: "Превью",
        Article.title: "Заголовок",
        Article.is_published: "Опубл.",
        Article.created_at: "Создана"
    }

    form_extra_fields = {
        "main_image_file": FileField("Загрузить обложку")
    }
    
    form_columns = [
        Article.title,
        Article.slug,
        "main_image_file",
        Article.content,
        Article.is_published
    ]

    create_template = "sqladmin/article_create.html"
    edit_template = "sqladmin/article_edit.html"

    def column_formatters(self):
        return {
            Article.main_image: lambda m, a: Markup(f'<img src="{m.main_image}" width="50">') if m.main_image else ""
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
