from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqladmin import Admin
from database import engine, init_db
from models import Product, Article
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
    column_list = [Product.id, Product.title, Product.price, Product.main_image, Product.categories]
    # По каким полям можно искать
    column_searchable_list = [Product.title, Product.description]
    
    # Сортировка по умолчанию: новые сверху
    column_default_sort = ("created_at", True)
    
    # --- UX Improvements ---
    
    # 1. Image Thumbnail
    def format_image(model, context, model_view):
        if model.main_image:
            return Markup(f'<img src="{model.main_image}" style="height: 50px; border-radius: 5px;">')
        return ""

    column_formatters = {
        Product.main_image: format_image
    }
    
    # 2. Categories as Tags
    # Для отображения списка категорий как тегов
    def format_categories(model, context, model_view):
        if model.categories:
            tags = "".join([f'<span class="badge bg-blue-lt me-1">{c}</span>' for c in model.categories])
            return Markup(tags)
        return ""
        
    column_formatters[Product.categories] = format_categories
    
    # 3. Custom Form Fields
    form_overrides = {
        "categories": TagListField
    }
    
    # Добавляем категории в список
    # column_list = [Product.id, Product.title, Product.price, Product.main_image, Product.categories] # This line is already defined above
    
    # Какие поля можно редактировать прямо в списке
    column_editable_list = ["price", "is_published"]
    
    # Custom form args to make categories easier to edit (as generic text field trying to parse JSON)
    # Note: A true TagField would require a custom WTForms field and overriding form_args more deeply.
    # For now, let's at least ensure the list view is pretty.

class ArticleAdmin(ModelView, model=Article):
    name = "Статья"
    name_plural = "Статьи"
    icon = "fa-solid fa-newspaper"
    column_list = [Article.title, Article.created_at]

# --- ЗАПУСК ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте создаем таблицы
    init_db()
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