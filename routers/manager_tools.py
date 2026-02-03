from typing import List, Optional
import os
import uuid
from datetime import datetime
import asyncio
import json
import ast
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import func
from schemas import BulkSpecUpdate, SpecsKeysResponse

from core.database import get_session
from core.config import settings
from core.security import get_current_username
from core.logger import logger
from models import Product, ProductImage

import httpx
from PIL import Image
from io import BytesIO
from duckduckgo_search import DDGS

router = APIRouter(prefix="/api/manager", tags=["manager"])

@router.get("/me", operation_id="read_user_me")
async def check_auth_status(username: str = Depends(get_current_username)):
    """
    Check if current user is authenticated.
    Returns username if valid, 401 otherwise (via Depends).
    """
    return {"username": username, "status": "authenticated"}

@router.post("/search-images", response_model=List[dict], operation_id="search_images")
async def search_images(
    q: str = Query(..., description="Query string for image search"),
    max_results: int = 20,
    username: str = Depends(get_current_username)
):
    """
    Search for images using DuckDuckGo.
    Returns a list of image objects: {image, width, height, ...}
    """
    logger.info(f"Manager {username} searching images for: {q}")
    
    try:
        # DBGS is synchronous, run in executor
        # Using updated approach for v6+
        results = await asyncio.to_thread(
            lambda: list(DDGS().images(q, max_results=max_results))
        )
        
        # Extract relevant fields
        images = []
        for r in results:
            if r.get('image'):
                images.append({
                    "image": r.get('image'),
                    "width": r.get('width'),
                    "height": r.get('height'),
                    "thumbnail": r.get('thumbnail')
                })
        return images
        
    except Exception as e:
        logger.error(f"Error searching images (DDG): {e}")
        # Return empty list or specific error instead of 500
        # Check if it is a rate limit or connection error
        if "Ratelimit" in str(e) or "403" in str(e):
             # Silently return empty list to not break UI, or handle specifically?
             # User requested: "Better to return empty list [] or understandable error".
             # Let's return empty list for graceful degradation.
             logger.warning(f"DDG Ratelimit hit for query: {q}")
             return []
        
        # For other errors, also fallback to empty list but log error
        return []

@router.post("/upload-image", operation_id="upload_image")
async def upload_image(
    url: str = Query(..., description="URL of the image to download"),
    product_id: int = Query(..., description="ID of the product to attach image to"),
    is_installation: bool = Query(False, description="Is this an installation photo?"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """
    Download image from URL, convert to WebP, save to local storage, 
    and create a ProductImage record linked to the product.
    """
    logger.info(f"Manager {username} uploading image for product {product_id} from {url}")
    
    # 1. Verify product exists
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Use helper. Default behavior for upload is to set main image if not installation
    # Use helper. Default behavior for upload is to set main image if not installation
    set_main = not is_installation
    return await _process_and_save_image(url, product_id, session, set_main=set_main, is_installation=is_installation)

async def _process_and_save_image(
    url: str, 
    product_id: int, 
    session: AsyncSession, 
    set_main: bool,
    is_installation: bool = False
):
    """Helper to download, convert, save, and link image."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
            image_content = resp.content
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to download image: {str(e)}")

    return await _save_image_from_bytes(image_content, product_id, session, set_main, is_installation)

async def _save_image_from_bytes(
    image_content: bytes,
    product_id: int,
    session: AsyncSession,
    set_main: bool,
    is_installation: bool = False
):
    """Process bytes (convert to WebP), save to disk, and link to product."""
    # 1. Process (WebP)
    try:
        def process_image(content):
            img = Image.open(BytesIO(content))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            output = BytesIO()
            img.save(output, format="WEBP", quality=85)
            return output.getvalue()

        webp_content = await asyncio.to_thread(process_image, image_content)
    except Exception as e:
        logger.error(f"Failed to process image: {e}")
        raise HTTPException(status_code=400, detail="Invalid image file")

    # 2. Save to Disk
    # Use root 'media' directory (Unified Storage)
    base_media_path = "media"
    if not os.path.exists(base_media_path):
        os.makedirs(base_media_path, exist_ok=True)
        
    product_media_dir = os.path.join(base_media_path, "products", str(product_id))
    os.makedirs(product_media_dir, exist_ok=True)
    
    filename = f"{uuid.uuid4()}.webp"
    file_path = os.path.join(product_media_dir, filename)
    
    try:
        async with asyncio.Lock():
            with open(file_path, "wb") as f:
                f.write(webp_content)
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save image file")

    # 3. Create DB Record
    relative_url = f"/media/products/{product_id}/{filename}"
    
    new_image = ProductImage(
        product_id=product_id,
        url=relative_url,
        is_installation_photo=is_installation
    )
    session.add(new_image)
    
    # Update main_image if requested
    if set_main and not is_installation:
        from sqlmodel import update
        statement = update(Product).where(Product.id == product_id).values(main_image=relative_url)
        await session.execute(statement)
        
    # Sync legacy images
    await _sync_legacy_images(session, product_id)
    
    await session.commit()
    await session.refresh(new_image)
    
    return {"url": relative_url, "id": new_image.id}

from fastapi import UploadFile, File

@router.post("/upload-local-images", operation_id="upload_local_images")
async def upload_local_images(
    product_id: int = Query(..., description="ID of the product"),
    files: List[UploadFile] = File(...),
    is_installation: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Upload multiple local files, convert to WebP, and attach to product."""
    logger.info(f"Manager {username} uploading {len(files)} local images for product {product_id}")
    
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    uploaded_images = []
    
    for file in files:
        try:
            content = await file.read()
            # Set main only if it's the first image and product has no main image? 
            # Or simplified: Local uploads don't auto-set main unless product has NONE.
            
            # Check if product has main image currently
            # (We need to re-fetch or trust the object, but object might be stale if we iterate)
            # Safe bet: separate query or just don't set main for batch uploads to be safe?
            # User request: "possibility to download multiple images". 
            # Let's say: first image in batch becomes main IF product has no main image.
            
            should_set_main = False
            if not product.main_image and not is_installation and len(uploaded_images) == 0:
                 should_set_main = True
                 
            result = await _save_image_from_bytes(content, product_id, session, set_main=should_set_main, is_installation=is_installation)
            uploaded_images.append(result)
            
            # If we set main, update local object to prevent next loop from trying
            if should_set_main:
                product.main_image = result["url"]
                
        except Exception as e:
            logger.error(f"Failed to upload file {file.filename}: {e}")
            # We continue with other files or Validation Error?
            # Let's continue and return what succeeded? Or fail all? 
            # For simplicity, fail on invalid file? Or skip?
            # Let's skip and log.
            pass
            
    return {"uploaded": len(uploaded_images), "images": uploaded_images}

async def _sync_legacy_images(session: AsyncSession, product_id: int):
    """Sync ProductImage records to Product.images JSON field."""
    product = await session.get(Product, product_id)
    if not product:
        return

    # Fetch all gallery images
    stmt = select(ProductImage).where(ProductImage.product_id == product_id)
    result = await session.execute(stmt)
    images = result.scalars().all()
    
    # Update JSON field with list of URLs
    # Filter out installation photos if we don't want them in main carousel? 
    # Usually main carousel shows all product photos. Installation photos might be separate?
    # For now, include all user-uploaded gallery images.
    product.images = [img.url for img in images if not img.is_installation_photo]
    session.add(product)

@router.post("/gallery/link-search-result", operation_id="link_search_result")
async def link_search_result(
    url: str = Query(..., description="URL of the image"),
    product_id: int = Query(..., description="ID of the product"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Add a search result image to gallery (download and link). Does NOT set as main image."""
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    return await _process_and_save_image(url, product_id, session, set_main=False)

@router.post("/gallery/set-main", operation_id="set_main_image")
async def set_main_image(
    image_id: int = Query(..., description="ID of the ProductImage to set as main"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Set a specific gallery image as the product's main image."""
    image = await session.get(ProductImage, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
        
    product = await session.get(Product, image.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    from sqlmodel import update
    statement = update(Product).where(Product.id == product.id).values(main_image=image.url)
    await session.execute(statement)
    await session.commit()
    return {"message": "Main image updated", "url": image.url}

@router.delete("/gallery/{image_id}", operation_id="delete_image")
async def delete_gallery_image(
    image_id: int,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Delete an image from the gallery (and disk)."""
    image = await session.get(ProductImage, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
        
    # Check if it's the main image
    product = await session.get(Product, image.product_id)
    if product and product.main_image == image.url:
         # Optional: Reset main image or forbid? 
         # Let's warn or clear it. Clearing is safer.
         from sqlmodel import update
         statement = update(Product).where(Product.id == product.id).values(main_image=None)
         await session.execute(statement)

    # Delete file from disk
    # url is like /media/products/123/uuid.webp
    # We need to map it back to web/public/media...
    try:
        if image.url.startswith("/media/"):
            relative_path = image.url.lstrip("/") # media/products/...
            # Assuming standard structure (root based)
            full_path = relative_path # it's already relative to root
            if os.path.exists(full_path):
                os.remove(full_path)
    except Exception as e:
        logger.error(f"Failed to delete file {image.url}: {e}")
        # Continue to delete DB record anyway

    await session.delete(image)
    # Sync legacy
    if product:
        await _sync_legacy_images(session, product.id)
    
    await session.commit()
    return {"message": "Image deleted"}

@router.get("/gallery/reuse-search", operation_id="reuse_search")
async def reuse_search(
    q: str = Query(..., min_length=2),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Search for products to reuse images from."""
    statement = select(Product).where(Product.title.ilike(f"%{q}%")).limit(10)
    result = await session.execute(statement)
    products = result.scalars().all()
    
    # Return simple list
    return [{"id": p.id, "title": p.title, "main_image": p.main_image} for p in products]

@router.post("/gallery/reuse-image", operation_id="reuse_image")
async def reuse_image(
    product_id: int = Query(...),
    source_image_url: str = Query(...),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Link an existing image URL to another product."""
    # Verify product
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Create new ProductImage with SAME URL
    new_image = ProductImage(
        product_id=product_id,
        url=source_image_url,
        is_installation_photo=False 
    )
    session.add(new_image)
    
    # Sync legacy
    await _sync_legacy_images(session, product_id)
    
    await session.commit()
    return {"message": "Image linked", "id": new_image.id}

@router.post("/cleanup-media", operation_id="cleanup_media")
async def cleanup_media(
    dry_run: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Delete orphaned media files not referenced in DB."""
    logger.info(f"Starting media cleanup (dry_run={dry_run}) by {username}")
    
    # 1. Gather all known images from DB
    # Product.main_image
    stmt_main = select(Product.main_image).where(Product.main_image != None)
    res_main = await session.execute(stmt_main)
    known_urls = set(res_main.scalars().all())
    
    # ProductImage.url
    stmt_gallery = select(ProductImage.url)
    res_gallery = await session.execute(stmt_gallery)
    known_urls.update(res_gallery.scalars().all())
    
    # 2. Scan disk
    base_dir = os.path.join("media", "products")
    deleted_count = 0
    reclaimed_bytes = 0
    
    if not os.path.exists(base_dir):
        return {"message": "Media directory not found", "deleted": 0}

    report = []

    for root, dirs, files in os.walk(base_dir):
        for file in files:
            full_path = os.path.join(root, file)
            # path relative to web/public, e.g. media/products/123/foo.webp
            # We match what's in DB: /media/products/... (often with leading slash)
            
            # Construct DB-style relative path
            # root is like media/products/123
            rel_dir = root # media/products/123
            db_path_rel = os.path.join(rel_dir, file) # media/products/123/foo.webp
            db_path_abs = "/" + db_path_rel # /media/products/123/foo.webp
            
            if db_path_abs not in known_urls and db_path_rel not in known_urls:
                # ORPHAN
                size = os.path.getsize(full_path)
                if not dry_run:
                    os.remove(full_path)
                
                deleted_count += 1
                reclaimed_bytes += size
                report.append(db_path_abs)

    return {
        "dry_run": dry_run,
        "deleted_count": deleted_count,
        "reclaimed_bytes": reclaimed_bytes,
        "files": report[:50] # Limit report size
    }

@router.post("/specs/bulk-update", operation_id="bulk_update_specs")
async def bulk_update_specs(
    payload: BulkSpecUpdate,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """
    Массовое добавление или обновление характеристик.
    Идеально для установки диаметров труб для целой серии кондиционеров сразу.
    """
    logger.info(f"Manager {username} bulk updating specs for {len(payload.product_ids)} products. Op: {payload.operation}")
    
    # Получаем товары
    stmt = select(Product).where(Product.id.in_(payload.product_ids))
    result = await session.execute(stmt)
    products = result.scalars().all()
    
    updated_count = 0
    
    for product in products:
        # Важно: создаем копию, чтобы SQLAlchemy детектил изменение JSON
        current_specs = dict(product.specs) if product.specs else {}
        
        if payload.operation == "replace":
            # Полная замена (опасно, но иногда нужно)
            current_specs = payload.specs
            
        elif payload.operation == "delete_keys":
            # Удаляем указанные ключи
            for key in payload.specs.keys():
                current_specs.pop(key, None)
                
        else: # "merge" (default)
            # Добавляем новые или обновляем существующие
            current_specs.update(payload.specs)
            
        # Присваиваем обратно
        product.specs = current_specs
        session.add(product)
        updated_count += 1
        
    await session.commit()
    
    return {
        "message": f"Updated specs for {updated_count} products", 
        "operation": payload.operation
    }

# --- MIGRATION / NORMALIZATION TOOLS ---

# Словарь перевода: Старый ключ (Onliner) -> Новый ключ (System)
LEGACY_TO_SYSTEM_MAP = {
    # Основное
    "Тип кондиционера": "type",
    "Дата выхода на рынок": "release_year",
    "Тип внутреннего блока": "indoor_type",
    "Режим работы": "modes",
    "Цвет": "color",
    "Wi-Fi": "wifi_ready",
    "Инверторная технология": "inverter",
    "Внутренний блок": "_delete_", # Мусорные поля помечаем на удаление
    "Наружный блок": "_delete_",
    "Пульт дистанционного управления": "_delete_", 

    # Производительность
    "Мощность охлаждения": "capacity_cooling_kw",
    "Мощность обогрева": "capacity_heating_kw",
    "Обслуживаемая площадь": "area_m2",
    "Потребляемая мощность при охлаждении": "power_cons_cooling_kw",
    "Потребляемая мощность при обогреве": "power_cons_heating_kw",
    "Энергоэффективность при охлаждении (EER)": "eer",
    "Энергоэффективность при обогреве (COP)": "cop",
    "Максимальный расход воздуха внутреннего блока": "airflow_max",

    # Трубы и монтаж
    "Максимальная длина магистрали": "pipe_max_length",
    "Перепад высот": "pipe_max_height",
    "Хладагент (фреон)": "freon_type",
    "Рабочая температура при охлаждении": "temp_range_cool",
    "Рабочая температура при обогреве": "temp_range_heat",

    # Шум
    "Шум внутреннего блока": "noise_indoor",
    "Шум наружного блока": "noise_outdoor",

    # Габариты (Onliner style - раздельные)
    "Ширина внутреннего блока": "width_indoor",
    "Высота внутреннего блока": "height_indoor",
    "Глубина внутреннего блока": "depth_indoor",
    "Ширина наружного блока": "width_outdoor",
    "Высота наружного блока": "height_outdoor",
    "Глубина наружного блока": "depth_outdoor",
    "Вес внутреннего блока": "weight_indoor",
    "Вес наружного блока": "weight_outdoor",
    
    # MDV (если вдруг уже есть кириллица с сайта MDV)
    "Модель внутреннего блока": "model_indoor",
    "Модель наружного блока": "model_outdoor",
}

def _clean_legacy_value(key: str, value: any):
    """Очищает значения (да -> True, удаление лишних единиц измерения)"""
    if isinstance(value, str):
        v_lower = value.lower().strip()
        
        # Булевы значения
        if v_lower == "да":
            return True
        if v_lower == "нет":
            return False
            
        # Чистка цифр (опционально, пока можно оставить строки для безопасности)
        # Если захочешь превратить "3.4 кВт" в число 3.4, раскомментируй:
        # if key in ["capacity_cooling_kw", "area_m2", "pipe_max_length"]:
        #     return re.sub(r"[^\d\.,-]", "", value).strip()
            
    return value

@router.post("/specs/normalize-legacy", operation_id="normalize_legacy_specs")
async def normalize_legacy_specs(
    dry_run: bool = Query(True, description="Если True - не сохраняет изменения в БД, только показывает пример"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """
    Массовая миграция характеристик.
    Переводит ключи Onliner (кириллица) в System (английский).
    """
    logger.info(f"Starting specs normalization (dry_run={dry_run}) by {username}")
    
    # Берем все товары, у которых есть specs
    stmt = select(Product).where(Product.specs != None)
    result = await session.execute(stmt)
    products = result.scalars().all()
    
    updated_count = 0
    preview_log = [] # Пример изменений для ответа
    
    for product in products:
        try:
            old_specs = product.specs
            
            # 1. Если это None - пропускаем
            if old_specs is None:
                continue

            if isinstance(old_specs, str):
                try:
                    # Попытка 1: Честный JSON
                    old_specs = json.loads(old_specs)
                except json.JSONDecodeError:
                    try:
                        # Попытка 2: Python dict string (одинарные кавычки)
                        old_specs = ast.literal_eval(old_specs)
                    except (ValueError, SyntaxError):
                        # Если совсем мусор
                        logger.warning(f"Product {product.id} has invalid format: {old_specs}")
                        continue

            # 3. Если после всех попыток это все еще не словарь - пропускаем
            if not isinstance(old_specs, dict):
                continue
                
            # --- Дальше старая логика ---
            new_specs = {}
            changed = False
            
            for old_key, val in old_specs.items(): # Теперь здесь точно словарь!
                new_key = LEGACY_TO_SYSTEM_MAP.get(old_key, old_key)
                
                if new_key == "_delete_":
                    changed = True
                    continue
                
                new_val = _clean_legacy_value(new_key, val)
                
                if new_key != old_key or new_val != val:
                    changed = True
                    
                new_specs[new_key] = new_val
                
            if changed:
                if not dry_run:
                    product.specs = new_specs
                    session.add(product)
                updated_count += 1
                if len(preview_log) < 5:
                    preview_log.append({
                        "id": product.id,
                        "before_sample": list(old_specs.keys())[:2],
                        "after_sample": list(new_specs.keys())[:2]
                    })
        except Exception as e:
            logger.error(f"Error normalizing product {product.id}: {e}")
            continue

    if not dry_run:
        await session.commit()
        
    return {
        "message": "Normalization complete",
        "dry_run": dry_run,
        "products_processed": len(products),
        "products_updated": updated_count,
        "sample_changes": preview_log
    }