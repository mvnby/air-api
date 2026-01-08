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
    
    # Что показывать в таблице
    column_list = [Product.id, Product.title, Product.price, Product.main_image]
    # По каким полям можно искать
    column_searchable_list = [Product.title, Product.description]
    
    # Сортировка по умолчанию
    column_default_sort = ("id", True)
    
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

# --- ИМПОРТ ТОВАРОВ (Endpoint) ---
@app.get("/admin/import_onliner")
async def import_onliner_form(request: Request):
    html = """
    <html>
        <head>
            <title>Импорт из Onliner</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { background-color: #f4f6f9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
                .card { box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: none; border-radius: 8px; }
            </style>
        </head>
        <body class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card p-4">
                        <h2 class="mb-4">📥 Импорт товара из Onliner</h2>
                        <form action="/admin/import_onliner" method="post">
                            <div class="mb-3">
                                <label for="url" class="form-label">Ссылка на товар в каталоге</label>
                                <input type="url" class="form-control" name="url" id="url" required placeholder="https://catalog.onliner.by/..." autofocus>
                                <div class="form-text">Введите полный URL страницы товара.</div>
                            </div>
                            <button type="submit" class="btn btn-primary w-100">Загрузить и создать</button>
                        </form>
                        <hr class="my-4">
                        <div class="text-center">
                            <a href="/admin/product/list" class="text-decoration-none">← Вернуться к списку товаров</a>
                        </div>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(html)

@app.post("/admin/import_onliner")
async def import_onliner_process(url: str = Form(...), session: Session = Depends(get_session)):
    try:
        data = await parse_onliner_product(url)
        
        # Создаем товар
        product = Product(
            title=data['title'],
            description=data['description'],
            price=data['price'],
            area=data['area'],
            main_image=data['main_image'],
            images=data.get('images', []),
            categories=data.get('categories', []),
            specs=data.get('specs', {}),
            is_published=False # Скрываем, пока админ не проверит
        )
        
        session.add(product)
        session.commit()
        session.refresh(product)
        
        # Редирект на редактирование созданного товара
        return RedirectResponse(url=f"/admin/product/details/{product.id}", status_code=303)
        
    except Exception as e:
        return HTMLResponse(f"""
            <div style="color: red; padding: 20px;">
                <h1>Ошибка импорта</h1>
                <p>{e}</p>
                <a href="/admin/import_onliner">Попробовать снова</a>
            </div>
        """)

# Подключаем админку
admin = Admin(app, engine, title="AirCon Admin")
admin.add_view(ProductAdmin)
admin.add_view(ArticleAdmin)

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