from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqladmin import Admin, ModelView
from database import engine, init_db
from models import Product, Article
from contextlib import asynccontextmanager
from fastapi import Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlmodel import select, Session
from database import get_session
from parser import parse_onliner_product

# --- НАСТРОЙКА АДМИНКИ ---

class ProductAdmin(ModelView, model=Product):
    """Настройки отображения товаров в админке"""
    name = "Товар"
    name_plural = "Товары"
    icon = "fa-solid fa-snowflake" # Иконка (FontAwesome)
    
    list_template = "product_list.html"
    
    # Что показывать в таблице
    column_list = [Product.id, Product.title, Product.price]
    # По каким полям можно искать
    column_searchable_list = [Product.title, Product.description]
    
    # Сортировка по умолчанию: новые сверху
    column_default_sort = ("created_at", True)
    
    # Какие поля можно редактировать прямо в списке
    # ИСПРАВЛЕНИЕ: Используем строки вместо объектов класса. 
    # Это часто решает проблему с отображением инпутов.
    column_editable_list = ["price", "is_published"]

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

# --- НАСТРОЙКА CORS (ВАЖНО!) ---
# Разрешаем запросы с любых сайтов (чтобы Astro мог забирать данные)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене лучше заменить на ["https://mvn.by"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/admin/import_onliner")
async def import_process(request: Request):
    form = await request.form()
    url = form.get("url")
    if not url:
        return RedirectResponse(url="/admin/product/list", status_code=303)
        
    try:
        data = await parse_onliner_product(url)
        with Session(engine) as session:
            product = Product(
                title=data['title'],
                description=data['description'],
                price=data['price'],
                area=data['area'],
                main_image=data['main_image'],
                images=data.get('images', []),
                categories=data.get('categories', []),
                specs=data.get('specs', {}),
                is_published=True
            )
            session.add(product)
            session.commit()
            session.refresh(product)
            # Редиректим сразу на детали нового товара
            return RedirectResponse(url=f"/admin/product/details/{product.id}", status_code=303)
    except Exception as e:
        # В случае ошибки возвращаемся в список
        print(f"Import error: {e}")
        return RedirectResponse(url="/admin/product/list", status_code=303)

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Подключаем админку
admin = Admin(app, engine, title="AirCon Admin", templates_dir=os.path.join(BASE_DIR, "templates"))
admin.add_view(ProductAdmin)
admin.add_view(ArticleAdmin)
# admin.add_view(ImportOnliner)  # Больше не нужно

# --- API (ПРИМЕР) ---
# Теперь API выглядит намного чище благодаря SQLModel

from sqlmodel import select, Session
from fastapi import Depends
from database import get_session

@app.get("/api/products")
def get_products(session: Session = Depends(get_session)):
    products = session.exec(select(Product)).all()
    return {"items": products}

@app.get("/api/products/{product_id}")
def get_product(product_id: int, session: Session = Depends(get_session)):
    product = session.get(Product, product_id)
    return product