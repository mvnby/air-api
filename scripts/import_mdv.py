import json
import asyncio
import os
import httpx
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

import sys
sys.path.append('.') 
from core.config import settings
from models import Product, ProductImage

# --- КОНФИГ ---
MEDIA_ROOT = "media/products"
os.makedirs(MEDIA_ROOT, exist_ok=True)

MODEL_REGEX = re.compile(r"\bMD[A-Z0-9]{1,5}-\d{2}[A-Z0-9]+\b", re.IGNORECASE)
RANGE_REGEX = re.compile(r"\(([\d,.]+)\s*-\s*([\d,.]+)\)")

MDV_MAP = {
    "COMPRESSOR_OPER_TYPE": "inverter_type",
    "COMPRESSOR_TYPE": "compressor_type",
    "COMPRESSOR_BRAND": "compressor_brand",
    "COOLING_NOM": "capacity_cooling_kw",
    "HEATING_NOM": "capacity_heating_kw",
    "COOLING_MIN": "capacity_cooling_min_kw",
    "COOLING_MAX": "capacity_cooling_max_kw",
    "HEATING_MIN": "capacity_heating_min_kw",
    "HEATING_MAX": "capacity_heating_max_kw",
    "SCOP": "scop",
    "SEER": "seer",
    "ENERGY_COOLING": "energy_class_cool",
    "ENERGY_HEATING": "energy_class_heat",
    "SIZE_INDOOR_WIDTH": "width_indoor",
    "SIZE_INDOOR_HEIGHT": "height_indoor",
    "SIZE_INDOOR_DEPTH": "depth_indoor",
    "WEIGHT_INDOOR_NETTO": "weight_indoor",
    "SIZE_OUTDOOR_WIDTH": "width_outdoor",
    "SIZE_OUTDOOR_HEIGHT": "height_outdoor", 
    "SIZE_OUTDOOR_DEPTH": "depth_outdoor",
    "WEIGHT_OUTDOOR_NETTO": "weight_outdoor",
    "NOISE_INDOOR": "noise_indoor", 
    "NOISE_OUTDOOR": "noise_outdoor",
    "MAX_PIPING_LENGTH": "pipe_max_length",
    "VERTICAL_DROP_MAX": "pipe_max_height",
    "COOLING_TYPE": "freon_type",
    "PIPE_LIQUID_SIZE_MM": "pipe_liquid",
    "PIPE_GAZ_SIZE_MM": "pipe_gas",
    "POWER_CABLE_RECOMMEND": "cable_power",
    "CABLE_BETWEEN_UNITS_REC": "cable_interconnect",
    "POWER_CONNECT": "power_supply_location",
    "TEMP_COOLING_LOW": "min_temp_cool",
    "TEMP_HEATING_LOW": "min_temp_heat",
}

def clean_value(val):
    if isinstance(val, str):
        return val.replace(",", ".").strip()
    return val

def parse_power_range(range_str):
    if not range_str: return None, None
    match = RANGE_REGEX.search(range_str)
    if match:
        return clean_value(match.group(1)), clean_value(match.group(2))
    return None, None

async def download_image(url: str, filename_base: str) -> str | None:
    if not url or "no_photo" in url: return None
    
    url = url.strip()
    if not url.startswith("http"):
        if url.startswith("/"):
            url = f"https://mdv-aircond.ru{url}"
        else:
            return None
            
    ext = url.split('.')[-1].split('?')[0]
    if len(ext) > 4: ext = "png"
    
    filename = f"{filename_base}.{ext}"
    local_path = os.path.join(MEDIA_ROOT, filename)
    db_path = f"/media/products/{filename}" 
    
    if os.path.exists(local_path):
        return db_path

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                print(f"      ⬇️ Скачано: {filename}")
                return db_path
            else:
                print(f"      ❌ Ошибка HTTP {resp.status_code}: {url}")
        except Exception as e:
            print(f"      ❌ Ошибка сети: {e}")
    return None

async def run_import():
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        with open("Бытовые сплит-системы MDV для дома и офиса.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ JSON файл не найден!")
        return

    print(f"🚀 Старт IMPORT v7.0 (Fix: Properties Lookup)! Items: {len(data)}")
    stats = {"updated": 0, "skipped": 0, "not_found": 0, "gallery_images": 0}

    async with async_session() as session:
        for item in data:
            model_key = item.get("PROPERTIES", {}).get("UNIT_INDOOR")
            if not model_key:
                match = MODEL_REGEX.search(item.get("NAME", ""))
                if match: model_key = match.group(0)
            
            if not model_key:
                stats["skipped"] += 1
                continue

            model_key = model_key.strip()
            
            stmt = select(Product).where(Product.title.ilike(f"%{model_key}%"))
            result = await session.execute(stmt)
            existing_product = result.scalars().first()

            if existing_product:
                props = item.get("PROPERTIES", {})
                new_specs = {}
                
                # Маппинг и спеки (оставляем как было, работает отлично)
                for json_key, sys_key in MDV_MAP.items():
                    val = props.get(json_key)
                    if val: new_specs[sys_key] = clean_value(val)
                
                p_cool_min, p_cool_max = parse_power_range(props.get("NOMINAL_POWER_COOLING_RANGE"))
                if p_cool_min: new_specs["power_cons_cooling_min_kw"] = p_cool_min
                if p_cool_max: new_specs["power_cons_cooling_max_kw"] = p_cool_max
                
                p_heat_min, p_heat_max = parse_power_range(props.get("NOMINAL_POWER_HEATING_RANGE"))
                if p_heat_min: new_specs["power_cons_heating_min_kw"] = p_heat_min
                if p_heat_max: new_specs["power_cons_heating_max_kw"] = p_heat_max

                if "height_outdoor" in new_specs and "depth_outdoor" in new_specs:
                    try:
                        h = float(new_specs["height_outdoor"])
                        d = float(new_specs["depth_outdoor"])
                        if d > h:
                            new_specs["height_outdoor"], new_specs["depth_outdoor"] = new_specs["depth_outdoor"], new_specs["height_outdoor"]
                    except ValueError: pass

                t_cool_low = props.get("TEMP_COOLING_LOW")
                t_cool_max = props.get("TEMP_COOLING_MAX")
                if t_cool_low and t_cool_max: new_specs["temp_range_cool"] = f"от {t_cool_low} до {t_cool_max} °C"

                t_heat_low = props.get("TEMP_HEATING_LOW")
                t_heat_high = props.get("TEMP_HEATING_HIGH")
                if t_heat_low and t_heat_high: new_specs["temp_range_heat"] = f"от {t_heat_low} до {t_heat_high} °C"
                
                if "Inverter" in props.get("COMPRESSOR_OPER_TYPE", "") or "Inverter" in item.get("NAME", ""): new_specs["inverter"] = True
                if props.get("UNIT_INDOOR"): new_specs["model_indoor"] = props.get("UNIT_INDOOR")
                if props.get("UNIT_OUTDOOR"): new_specs["model_outdoor"] = props.get("UNIT_OUTDOOR")

                old_specs = existing_product.specs or {}
                if isinstance(old_specs, str):
                    import ast
                    try: old_specs = ast.literal_eval(old_specs)
                    except: old_specs = {}
                updated_specs = old_specs.copy()
                updated_specs.update(new_specs)
                existing_product.specs = updated_specs
                flag_modified(existing_product, "specs")

                # Фото (Главное) - оно в корне
                img_url = item.get("PREVIEW_PICTURE")
                if img_url:
                    path = await download_image(img_url, existing_product.slug)
                    if path: existing_product.main_image = path
                
                # --- ГАЛЕРЕЯ (FIX!) ---
                # Ищем внутри PROPS, а не в корне!
                more_photos = props.get("MORE_PHOTO")
                if more_photos:
                    gallery_urls = [u.strip() for u in more_photos.split(',')]
                    
                    for idx, url in enumerate(gallery_urls):
                        if not url: continue
                        
                        g_path = await download_image(url, f"{existing_product.slug}_gallery_{idx+1}")
                        
                        if g_path:
                            stmt_img = select(ProductImage).where(
                                ProductImage.product_id == existing_product.id,
                                ProductImage.url == g_path
                            )
                            existing_img = await session.execute(stmt_img)
                            
                            if not existing_img.scalars().first():
                                new_img = ProductImage(
                                    product_id=existing_product.id,
                                    url=g_path,
                                    is_installation_photo=False 
                                )
                                session.add(new_img)
                                stats["gallery_images"] += 1
                                print(f"      ✅ Добавлено фото: {existing_product.title[:20]}... -> {idx+1}")

                session.add(existing_product)
                await session.commit()
                stats["updated"] += 1
            else:
                stats["not_found"] += 1
        
    print(f"\n🏁 Готово! Обновлено товаров: {stats['updated']}. Новых фото в галерее: {stats['gallery_images']}")

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_import())
