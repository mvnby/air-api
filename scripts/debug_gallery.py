import asyncio
import json
import os
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import sys

sys.path.append('.')
from core.config import settings
from models import Product, ProductImage

async def check_gallery():
    # 1. Подключаемся
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("🔍 --- ДИАГНОСТИКА ГАЛЕРЕИ ---")

    async with async_session() as session:
        # 2. Проверяем, существует ли таблица вообще
        try:
            # Простой SQL запрос для проверки кол-ва записей
            cnt = await session.execute(text("SELECT count(*) FROM product_image"))
            total_images = cnt.scalar()
            print(f"✅ Таблица 'product_image' существует. Всего записей: {total_images}")
        except Exception as e:
            print(f"❌ ОШИБКА: Таблица 'product_image' не найдена или недоступна!\n{e}")
            print("👉 Выполнили ли вы миграции? (alembic revision... / alembic upgrade...)")
            return

        # 3. Ищем тестовый товар
        target_slug = "mdsc-07hrdn8" # Пример товара с галереей
        stmt = select(Product).where(Product.title.ilike("%MDSC-07HRDN8%"))
        res = await session.execute(stmt)
        product = res.scalars().first()

        if not product:
            print(f"❌ Товар {target_slug} не найден в базе!")
            return
        
        print(f"📦 Товар найден: id={product.id}, title='{product.title}'")

        # 4. Смотрим, что у него сейчас в галерее (в БД)
        stmt_img = select(ProductImage).where(ProductImage.product_id == product.id)
        imgs = await session.execute(stmt_img)
        existing_images = imgs.scalars().all()
        
        print(f"🖼  Фото в базе (ProductImage): {len(existing_images)} шт.")
        for img in existing_images:
            print(f"   - id={img.id}: {img.url}")

        # 5. Смотрим, что у него в JSON файле
        try:
            with open("Бытовые сплит-системы MDV для дома и офиса.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Ищем этот товар в JSON
            json_item = next((i for i in data if "MDSC-07HRDN8" in i.get("PROPERTIES", {}).get("UNIT_INDOOR", "")), None)
            
            if json_item:
                raw_more_photo = json_item.get("MORE_PHOTO")
                print(f"📄 Данные в JSON 'MORE_PHOTO':")
                if raw_more_photo:
                    urls = raw_more_photo.split(',')
                    print(f"   Всего ссылок: {len(urls)}")
                    print(f"   Первая ссылка: {urls[0][:50]}...")
                else:
                    print("   ⚠️ Поле MORE_PHOTO пустое или отсутствует!")
            else:
                print("❌ Товар не найден в JSON файле (по UNIT_INDOOR)!")

        except FileNotFoundError:
            print("❌ Файл JSON не найден!")

        # 6. Проверяем файлы на диске
        if existing_images:
            first_img_path = "static" + existing_images[0].url if not existing_images[0].url.startswith("/") else "." + existing_images[0].url
            # Убираем ведущий слеш для проверки пути, если нужно
            if first_img_path.startswith("./"): first_img_path = first_img_path[2:]
            
            print(f"📂 Проверка файла на диске: {first_img_path}")
            if os.path.exists(first_img_path):
                print("   ✅ Файл физически существует.")
            else:
                print("   ❌ Файл НЕ найден на диске! (Путь неверен?)")

if __name__ == "__main__":
    asyncio.run(check_gallery())