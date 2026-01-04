from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import get_all_products, get_product_by_id, get_products_by_area

# Создаем приложение
app = FastAPI(
    title="Air Conditioners API",
    description="API для магазина кондиционеров",
    version="1.0.0"
)

# --- НАСТРОЙКА CORS (ВАЖНО!) ---
# Разрешаем запросы с любых сайтов (для начала).
# Когда запустишь сайт, лучше заменить ["*"] на ["https://mvn.by"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешить всем
    allow_credentials=True,
    allow_methods=["*"],  # Разрешить любые методы (GET, POST...)
    allow_headers=["*"],
)

# --- ЭНДПОИНТЫ (РУЧКИ API) ---

@app.get("/")
def read_root():
    """Проверка, что API работает"""
    return {"status": "ok", "message": "Сервер кондиционеров работает! ❄️"}

@app.get("/api/products")
def get_products():
    """Отдает полный список товаров"""
    products = get_all_products()
    return {
        "count": len(products),
        "items": products
    }

@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    """Отдает один товар по ID"""
    product = get_product_by_id(product_id)
    if product:
        return product
    return {"error": "Товар не найден"}

@app.get("/api/filter")
def filter_products(area: int):
    """Фильтр по площади: /api/filter?area=25"""
    products = get_products_by_area(area)
    return {
        "count": len(products),
        "area_requested": area,
        "items": products
    }