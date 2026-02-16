import asyncio
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
import sys

sys.path.append('.')
from core.config import settings
from models import Product
from services.spec_normalizer import normalize_specs

# --- НАСТРОЙКИ ---
KEEP_UNITS = True  # True = Оставляем "кВт", "мм". False = Чистим до числа.
# Сейчас ставим True, чтобы на сайте было красиво сразу!



async def run_normalize():
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print(f"🧹 Старт нормализации v2 (Keep Units: {KEEP_UNITS})...")
    
    async with async_session() as session:
        result = await session.execute(
            select(Product).options(selectinload(Product.tags))
        )
        products = result.scalars().all()
        
        updated_count = 0
        
        for p in products:
            # Важно: Работаем с копией
            old_specs = p.specs.copy() if isinstance(p.specs, dict) else {}
            wifi_tag_slugs = [
                tag.slug
                for tag in (p.tags or [])
                if tag.slug in {"wifi-builtin", "wifi-ready"}
            ]
            
            # Use the new shared logic
            new_specs = normalize_specs(
                old_specs,
                keep_units=KEEP_UNITS,
                wifi_tag_slugs=wifi_tag_slugs,
                strict_wifi_from_tags=True,
            )
            
            # Check if updated (simple dict comparison)
            if new_specs != old_specs:
                p.specs = new_specs
                flag_modified(p, "specs")
                updated_count += 1
        
        await session.commit()
        print(f"🏁 Готово! Исправлено товаров: {updated_count}")

if __name__ == "__main__":
    asyncio.run(run_normalize())
