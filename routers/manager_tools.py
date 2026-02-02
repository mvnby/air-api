from typing import List, Optional
import os
import uuid
from datetime import datetime
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.database import get_session
from core.config import settings
from core.security import get_current_username
from core.logger import logger
from models import Product, ProductImage

import httpx
from PIL import Image
from io import BytesIO
from ddgs import DDGS

router = APIRouter(prefix="/api/manager", tags=["manager"])

@router.post("/search-images", response_model=List[dict])
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
        logger.error(f"Error searching images: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )

@router.post("/upload-image")
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
    # 1. Download
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
            image_content = resp.content
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to download image: {str(e)}")

    # 2. Process (WebP)
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

    # 3. Save to Disk
    base_media_path = os.path.join("web", "public", "media")
    if not os.path.exists(base_media_path):
        base_media_path = "media"
        
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

    # 4. Create DB Record
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

@router.post("/gallery/link-search-result")
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

@router.post("/gallery/set-main")
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

@router.delete("/gallery/{image_id}")
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
            # Assuming standard structure
            base_path = os.path.join("web", "public")
            full_path = os.path.join(base_path, relative_path)
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

@router.get("/gallery/reuse-search")
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

@router.post("/gallery/reuse-image")
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

@router.post("/cleanup-media")
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
    base_dir = os.path.join("web", "public", "media", "products")
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
            # root is like web/public/media/products/123
            rel_dir = os.path.relpath(root, os.path.join("web", "public")) # media/products/123
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
