from typing import Any
from sqladmin import ModelView
from wtforms import FileField, TextAreaField
from slugify import slugify
from markupsafe import Markup

from models import Article
from services.article_service import ArticleService
from core.database import async_session_maker

class ArticleAdmin(ModelView, model=Article):
    name = "Статья"
    name_plural = "Статьи"
    icon = "fa-solid fa-newspaper"
    extra_js = ["/static/js/admin_article_upload.js"]
    
    column_list = [
        "id", "cover_image", "title", "is_published", "created_at"
    ]
    
    column_labels = {
        "cover_image": "Превью",
        "title": "Заголовок",
        "is_published": "Опубл.",
        "created_at": "Создана"
    }

    form_extra_fields = {
        "cover_image_file": FileField("Загрузить обложку")
    }
    
    form_columns = [
        "title", "slug", "content", "is_published"
    ]

    form_create_rules = [
        "title"
    ]
    
    # Restore full fields for editing
    form_edit_rules = [
        "title", "slug", "cover_image_file", "content", "is_published"
    ]

    form_overrides = {
        "content": TextAreaField
    }

    async def scaffold_form(self, rules=None, **kwargs):
        # We must pass rules to super() so strict forms (like ['title']) use only those fields.
        # However, we must filter out non-model fields (like 'cover_image_file') before passing to super,
        # otherwise sqladmin might error trying to find them on the model.
        
        model_rules = rules
        if rules:
            model_rules = [r for r in rules if r != "cover_image_file"]
            
        form_class = await super().scaffold_form(rules=model_rules)
        
        # Only attach the extra field if it was requested in the original rules
        # (or if rules is None, implying default/full form)
        if rules is None or "cover_image_file" in rules:
            form_class.cover_image_file = self.form_extra_fields["cover_image_file"]
            
        return form_class

    create_template = "sqladmin/article_create.html"
    edit_template = "sqladmin/article_edit.html"

    column_formatters = {
        "cover_image": lambda m, c: Markup(f'<img src="{m.cover_image}" width="50">') if m.cover_image else ""
    }

    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Any) -> None:
        # 1. Handle Slug
        if not data.get("slug"):
            data["slug"] = slugify(data.get("title", "article"))
            
        # 2. Handle Required Content
        if is_created and "content" not in data:
            data["content"] = ""

        # Remove file field from data
        if "cover_image_file" in data:
            del data["cover_image_file"]
        
        # 2. Handle Image Upload
        form = await request.form()
        upload_field = form.get("cover_image_file")
        
        if upload_field and hasattr(upload_field, 'filename') and upload_field.filename:
            # For new articles, save first to get ID
            if is_created:
                await super().on_model_change(data, model, is_created, request)
                
                # Now upload image
                file_bytes = await upload_field.read()
                async with async_session_maker() as session:
                    web_path = await ArticleService.save_cover_image(
                        session=session,
                        article_id=model.id,
                        file_bytes=file_bytes,
                        filename=upload_field.filename
                    )
                # Image is already saved to DB by ArticleService
            else:
                # For existing articles, update data before saving
                file_bytes = await upload_field.read()
                async with async_session_maker() as session:
                    # Get article to get slug
                    from sqlmodel import select
                    from models import Article
                    stmt = select(Article).where(Article.id == model.id)
                    result = await session.execute(stmt)
                    article = result.scalar_one_or_none()
                    
                    if article:
                        # Save image
                        from services.image_service import ImageService
                        db_path = await ImageService.save_image(
                            file_bytes=file_bytes,
                            entity_type="articles",
                            slug=article.slug,
                            filename=upload_field.filename
                        )
                        # Update data dict so it gets saved
                        data["cover_image"] = ImageService.get_web_path(db_path)
                
                # Now save with updated data
                await super().on_model_change(data, model, is_created, request)
        else:
            # No image upload, just save normally
            await super().on_model_change(data, model, is_created, request)
