import asyncio
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
import sys

sys.path.append('.')
from core.config import settings
from models import Product

# 1. Маппинг (Русский -> Системный)
KEY_MAP = {
    # Основное
    "Тип кондиционера": "type",
    "Режим работы": "modes",
    "Обслуживаемая площадь": "area_m2",
    "Цвет": "color",
    "Хладагент (фреон)": "freon_type",
    "Инверторная технология": "inverter", # Значения "да/нет" обработаем отдельно
    
    # Мощность
    "Мощность охлаждения": "capacity_cooling_kw",
    "Мощность обогрева": "capacity_heating_kw",
    "Потребляемая мощность при охлаждении": "power_cons_cooling_kw",
    "Потребляемая мощность при обогреве": "power_cons_heating_kw",
    
    # Эффективность
    "Энергоэффективность при охлаждении (EER)": "eer",
    "Энергоэффективность при обогреве (COP)": "cop",
    
    # Шум
    "Шум внутреннего блока": "noise_indoor",
    "Шум наружного блока": "noise_outdoor",
    
    # Габариты Внутренний
    "Ширина внутреннего блока": "width_indoor",
    "Высота внутреннего блока": "height_indoor",
    "Глубина внутреннего блока": "depth_indoor",
    "Вес внутреннего блока": "weight_indoor",
    
    # Габариты Наружный
    "Ширина наружного блока": "width_outdoor",
    "Высота наружного блока": "height_outdoor",
    "Глубина наружного блока": "depth_outdoor",
    "Вес наружного блока": "weight_outdoor",
    
    # Монтаж
    "Максимальная длина магистрали": "pipe_max_length",
    "Перепад высот": "pipe_max_height",
    "Диаметр жидкостной трубы": "pipe_liquid",
    "Диаметр газовой трубы": "pipe_gas",
    
    # Температуры
    "Рабочая температура при охлаждении": "temp_range_cool",
    "Рабочая температура при обогреве": "temp_range_heat",
    
    # Функции (Wi-Fi и т.д.)
    "Wi-Fi": "wifi_ready",
    "Максимальный расход воздуха внутреннего блока": "airflow_max"
}

# Регулярка для очистки чисел (оставляет цифры, точки, диапазоны)
CLEAN_NUM_REGEX = re.compile(r"[^\d.,\-—]") 

def clean_value(key, val):
    if not isinstance(val, str):
        return val
        
    val = val.strip()
    
    # 1. Логика для Инвертора
    if key == "inverter":
        if val.lower() == "да": return True
        if val.lower() == "нет": return False
        return val

    # 2. Чистим числа (убираем "кВт", "мм", "кг", "м2")
    # Список ключей, которые должны быть числами
    numeric_keys = [
        "capacity_", "power_cons_", "width_", "height_", "depth_", "weight_", 
        "pipe_max_", "eer", "cop"
    ]
    
    is_numeric = any(k in key for k in numeric_keys)
    
    if is_numeric:
        # Убираем всё кроме цифр, точек и запятых
        # "10.55 кВт" -> "10.55"
        # "1 300" -> "1300"
        clean = val.replace(" ", "").replace("кВт", "").replace("мм", "").replace("кг", "").replace("м2", "").replace("м", "")
        # Меняем запятую на точку
        clean = clean.replace(",", ".")
        return clean

    return val

async def run_normalize():
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("🧹 Старт нормализации характеристик...")
    
    async with async_session() as session:
        # Берем ВСЕ товары
        result = await session.execute(select(Product))
        products = result.scalars().all()
        
        updated_count = 0
        
        for p in products:
            if not p.specs: continue
            
            # Делаем копию спеков
            old_specs = p.specs.copy() if isinstance(p.specs, dict) else {}
            new_specs = old_specs.copy()
            
            has_changes = False
            
            # Проходим по старым русским ключам
            for rus_key, sys_key in KEY_MAP.items():
                if rus_key in old_specs:
                    raw_val = old_specs[rus_key]
                    
                    # Чистим значение
                    clean_val = clean_value(sys_key, raw_val)
                    
                    # Записываем в новый ключ
                    new_specs[sys_key] = clean_val
                    
                    # Удаляем старый русский ключ (чтобы не дублировалось)
                    # Если хочешь оставить и старые - закомментируй следующую строку
                    del new_specs[rus_key] 
                    
                    has_changes = True

            if has_changes:
                p.specs = new_specs
                flag_modified(p, "specs")
                updated_count += 1
                # print(f"✅ Updated: {p.title}")
        
        await session.commit()
        print(f"🏁 Готово! Обработано товаров: {updated_count}")

if __name__ == "__main__":
    asyncio.run(run_normalize())