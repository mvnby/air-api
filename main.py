from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqladmin import Admin
from database import engine, init_db
from models import Product, Article, Tag, TagGroup
from contextlib import asynccontextmanager
import os

# Routers
from routers import admin as admin_router
from routers import api as api_router

# Admin Views (можно вынести в отдельный файл admin_views.py, но пока оставим тут для простоты)
from sqladmin import ModelView
from markupsafe import Markup

from starlette.middleware.sessions import SessionMiddleware
from forms import TagListField

class ProductAdmin(ModelView, model=Product):
    """Настройки отображения товаров в админке"""
    name = "Товар"
    name_plural = "Товары"
    icon = "fa-solid fa-snowflake" # Иконка (FontAwesome)
    
    list_template = "product_list.html"
    
    # Что показывать в таблице
    column_list = [Product.id, Product.title, Product.price, Product.main_image, Product.tags]
    # По каким полям можно искать
    column_searchable_list = [Product.title, Product.description]
    
    # Сортировка по умолчанию: новые сверху
    column_default_sort = ("created_at", True)
    
    # Eager load tags for list view to prevent async lazy load issues
    def list_query(self, request):
        query = super().list_query(request)
        from sqlalchemy.orm import selectinload
        return query.options(selectinload(self.model.tags))

    def detail_query(self, request):
        query = super().detail_query(request)
        from sqlalchemy.orm import selectinload
        return query.options(selectinload(self.model.tags))

    def edit_query(self, request):
        query = super().edit_query(request)
        from sqlalchemy.orm import selectinload
        return query.options(selectinload(self.model.tags))
    
    # --- UX Improvements ---
    
    # 1. Image Thumbnail
    def format_image(model, context):
        if model.main_image:
            return Markup(f'<img src="{model.main_image}" style="height: 50px; border-radius: 5px;">')
        return ""

    # 2. Categories as Tags
    def format_tags(model, context):
        if model.tags:
            # Show first 3 tags then ...
            display_tags = model.tags[:3]
            html = "".join([f'<span class="badge bg-blue-lt me-1">{t.title}</span>' for t in display_tags])
            if len(model.tags) > 3:
                html += f'<span class="badge bg-gray-lt">+{len(model.tags)-3}</span>'
            return Markup(html)
        return ""

    column_formatters = {
        Product.main_image: format_image,
        Product.tags: format_tags
    }
    
    # Strategy: Override the 'tags' relationship field directly.
    # TagListField accepts **kwargs to handle relationship args from SQLAdmin.
    
    form_overrides = {
        "tags": TagListField
    }
    
    form_columns = [
        "title", "description", "price", "old_price", "area", 
        "main_image", "images", "tags", "specs", "is_published"
    ]
    
    # Custom handler: process tags manually
    async def on_model_change(self, data, model, is_created, request):
        if "tags" in data:
            model._temp_tag_names = data["tags"]
            del data["tags"]

    async def after_model_change(self, data, model, is_created, request):
        if hasattr(model, "_temp_tag_names"):
            tag_names = model._temp_tag_names
            delattr(model, "_temp_tag_names") 
            
            from database import async_session_maker
            from models import Product, Tag
            from sqlmodel import select
            from sqlalchemy.orm import selectinload
            import slugify
            
            try:
                # Use a completely new, independent session to update categories
                async with async_session_maker() as session:
                    # 1. Re-fetch the product to attach it to this session
                    stmt = select(Product).where(Product.id == model.id).options(selectinload(Product.tags))
                    result = await session.execute(stmt)
                    db_product = result.scalar_one()
                    
                    # 2. Resolve Tags
                    new_tags = []
                    for name in tag_names:
                        name = name.strip()
                        if not name: continue
                        
                        # Find existing Tag by title
                        c_stmt = select(Tag).where(Tag.title == name)
                        c_res = await session.execute(c_stmt)
                        tag = c_res.scalar_one_or_none()
                        
                        if not tag:
                            # Create new Tag
                            slug = slugify.slugify(name)
                            tag = Tag(title=name, slug=slug, is_public=True)
                            session.add(tag) 
                        
                        new_tags.append(tag)
                    
                    # 3. Assign to product
                    db_product.tags = new_tags
                    
                    # 4. Commit changes
                    await session.commit()
                    
            except Exception as e:
                print(f"ERROR in after_model_change: {e}")
                pass

    # Какие поля можно редактировать прямо в списке
    column_editable_list = ["price", "is_published"]

class ArticleAdmin(ModelView, model=Article):
    name = "Статья"
    name_plural = "Статьи"
    icon = "fa-solid fa-newspaper"
    column_list = [Article.title, Article.created_at]

class TagGroupAdmin(ModelView, model=TagGroup):
    name = "Группа тегов"
    name_plural = "Группы тегов"
    icon = "fa-solid fa-layer-group"
    column_list = [TagGroup.title, TagGroup.slug, TagGroup.sort_order]

class TagAdmin(ModelView, model=Tag):
    name = "Тег"
    name_plural = "Теги"
    icon = "fa-solid fa-tag"
    column_list = [Tag.title, Tag.slug, Tag.group, Tag.reliability_score]
    form_columns = ["group", "title", "slug", "is_public", "is_filter", "sort_order", "ai_snippet", "reliability_score"]

# --- ЗАПУСК ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте создаем таблицы
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)

# --- MIDDLEWARE ---
app.add_middleware(SessionMiddleware, secret_key="super-secret-key") # Change in production

# --- НАСТРОЙКА CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(admin_router.router)
app.include_router(api_router.router)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Подключаем админку
admin = Admin(app, engine, title="AirCon Admin", templates_dir=os.path.join(BASE_DIR, "templates"))
admin.add_view(ProductAdmin)
admin.add_view(ArticleAdmin)
admin.add_view(TagGroupAdmin)
admin.add_view(TagAdmin)