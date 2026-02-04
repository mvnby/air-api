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

# --- НАСТРОЙКИ ---
KEEP_UNITS = True  # True = Оставляем "кВт", "мм". False = Чистим до числа.
# Сейчас ставим True, чтобы на сайте было красиво сразу!

# 1. Маппинг (Русский -> Системный)
KEY_MAP = {
    # --- ОСНОВНОЕ ---
    "Тип кондиционера": "type",
    "Тип внутреннего блока": "indoor_type",  # <--- ДОБАВИЛ!
    "Режим работы": "modes",
    "Обслуживаемая площадь": "area_m2",
    "Цвет": "color",
    "Хладагент (фреон)": "freon_type",
    "Инверторная технология": "inverter",
    
    # --- УПРАВЛЕНИЕ ---
    "Wi-Fi": "wifi_ready",
    "Пульт дистанционного управления": "remote_control", # <--- ДОБАВИЛ
    "Таймер включения/выключения": "timer",
    "Регулировка направления воздушного потока": "airflow_direction",
    "Регулировка скорости вращения вентилятора": "fan_speed",
    "Авторестарт после пропадания питания": "autorestart",
    "Турбо-режим": "turbo_mode",
    "Режим «Сон»": "sleep_mode",
    "Осушение воздуха": "dehumidification",

    # --- МОЩНОСТЬ ---
    "Мощность охлаждения": "capacity_cooling_kw",
    "Мощность обогрева": "capacity_heating_kw",
    "Потребляемая мощность при охлаждении": "power_cons_cooling_kw",
    "Потребляемая мощность при обогреве": "power_cons_heating_kw",
    
    # --- ЭФФЕКТИВНОСТЬ ---
    "Энергоэффективность при охлаждении (EER)": "eer",
    "Энергоэффективность при обогреве (COP)": "cop",
    
    # --- ШУМ ---
    "Шум внутреннего блока": "noise_indoor",
    "Шум наружного блока": "noise_outdoor",
    
    # --- ГАБАРИТЫ ВНУТРЕННИЙ ---
    "Ширина внутреннего блока": "width_indoor",
    "Высота внутреннего блока": "height_indoor",
    "Глубина внутреннего блока": "depth_indoor",
    "Вес внутреннего блока": "weight_indoor",
    
    # --- ГАБАРИТЫ НАРУЖНЫЙ ---
    "Ширина наружного блока": "width_outdoor",
    "Высота наружного блока": "height_outdoor",
    "Глубина наружного блока": "depth_outdoor",
    "Вес наружного блока": "weight_outdoor",
    
    # --- МОНТАЖ ---
    "Максимальная длина магистрали": "pipe_max_length",
    "Перепад высот": "pipe_max_height",
    "Диаметр жидкостной трубы": "pipe_liquid",
    "Диаметр газовой трубы": "pipe_gas",
    
    # --- ТЕМПЕРАТУРЫ ---
    "Рабочая температура при охлаждении": "temp_range_cool",
    "Рабочая температура при обогреве": "temp_range_heat",
    
    "Максимальный расход воздуха внутреннего блока": "airflow_max"
}

def clean_value(key, val):
    if not isinstance(val, str):
        return val
        
    val_lower = val.lower().strip()

    # 1. Логика для Булевых (Да/Нет)
    # Сюда попадают: inverter, wifi_ready, remote_control и все режимы
    boolean_keys = [
        "inverter", "wifi_ready", "remote_control", "timer", 
        "autorestart", "turbo_mode", "sleep_mode", "dehumidification",
        "airflow_direction", "fan_speed"
    ]
    
    if key in boolean_keys:
        if "да" in val_lower or "есть" in val_lower or "поддерживается" in val_lower:
            return True
        if "нет" in val_lower or "отсутствует" in val_lower:
            return False
        return val # Если там что-то сложное, оставляем как есть

    # 2. Чистка чисел (Только если KEEP_UNITS = False)
    if not KEEP_UNITS:
        numeric_keys = [
            "capacity_", "power_cons_", "width_", "height_", "depth_", "weight_", 
            "pipe_max_", "eer", "cop"
        ]
        is_numeric = any(k in key for k in numeric_keys)
        
        if is_numeric:
            # Агрессивная чистка: "2.5 кВт" -> "2.5"
            clean = val.replace(" ", "").replace("кВт", "").replace("мм", "").replace("кг", "").replace("м2", "").replace("м", "")
            clean = clean.replace(",", ".")
            return clean

    # Если KEEP_UNITS = True, просто убираем лишние пробелы и меняем запятые на точки (для красоты)
    if isinstance(val, str):
        # Меняем "2,5" на "2.5", но оставляем "кВт"
        # Аккуратно: заменяем запятую только если она между цифрами
        val = re.sub(r'(\d),(\d)', r'\1.\2', val)
        return val.strip()

    return val

async def run_normalize():
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print(f"🧹 Старт нормализации v2 (Keep Units: {KEEP_UNITS})...")
    
    async with async_session() as session:
        result = await session.execute(select(Product))
        products = result.scalars().all()
        
        updated_count = 0
        
        for p in products:
            if not p.specs: continue
            
            # Важно: Работаем с копией
            old_specs = p.specs.copy() if isinstance(p.specs, dict) else {}
            new_specs = old_specs.copy()
            
            has_changes = False
            
            # Проходим по старым русским ключам
            for rus_key, sys_key in KEY_MAP.items():
                if rus_key in old_specs:
                    raw_val = old_specs[rus_key]
                    
                    # Чистим / Конвертируем
                    clean_val = clean_value(sys_key, raw_val)
                    
                    # Записываем новый ключ
                    new_specs[sys_key] = clean_val
                    
                    # Удаляем старый (чтобы не было дублей)
                    del new_specs[rus_key] 
                    
                    has_changes = True
            
            # Дополнительно: Пробежимся по УЖЕ существующим системным ключам
            # (на случай, если они уже есть, но "голые", а мы хотим вернуть форматирование - 
            # хотя вернуть "кВт" из числа "2.5" скриптом сложно, лучше просто перезалить базу
            # или оставить как есть. Этот скрипт чинит именно Legacy ключи).

            if has_changes:
                p.specs = new_specs
                flag_modified(p, "specs")
                updated_count += 1
        
        await session.commit()
        print(f"🏁 Готово! Исправлено товаров: {updated_count}")

if __name__ == "__main__":
    asyncio.run(run_normalize())