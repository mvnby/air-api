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

@router.post("/search-images", response_model=List[str])
async def search_images(
    q: str = Query(..., description="Query string for image search"),
    max_results: int = 20,
    username: str = Depends(get_current_username)
):
    """
    Search for images using DuckDuckGo.
    Returns a list of image URLs.
    """
    logger.info(f"Manager {username} searching images for: {q}")
    
    try:
        # DBGS is synchronous, run in executor
        results = await asyncio.to_thread(
            lambda: list(DDGS().images(q, max_results=max_results))
        )
        # Extract URLs
        urls = [r.get('image') for r in results if r.get('image')]
        return urls
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

    # 2. Download Image
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
            image_content = resp.content
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to download image: {str(e)}")

    # 3. Process Image (Convert to WebP)
    try:
        def process_image(content):
            img = Image.open(BytesIO(content))
            # Convert to RGB if necessary (e.g. for PNGs with alpha)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            output = BytesIO()
            img.save(output, format="WEBP", quality=85)
            return output.getvalue()

        webp_content = await asyncio.to_thread(process_image, image_content)
    except Exception as e:
        logger.error(f"Failed to process image: {e}")
        raise HTTPException(status_code=400, detail="Invalid image file or processing error")

    # 4. Save to Disk
    # Path: web/public/media/products/{product_id}/{uuid}.webp (relative for DB: /media/products/...)
    
    # Base media path is now web/public/media
    base_media_path = os.path.join("web", "public", "media")
    if not os.path.exists(base_media_path):
        # Fallback if we are running in a context where web/public/media doesn't exist (unlikely in dev)
        base_media_path = "media"
        
    product_media_dir = os.path.join(base_media_path, "products", str(product_id))
    os.makedirs(product_media_dir, exist_ok=True)
    
    filename = f"{uuid.uuid4()}.webp"
    file_path = os.path.join(product_media_dir, filename)
    
    try:
        async with asyncio.Lock(): # Simple lock for file writing safety if needed, though mostly unique filenames
            with open(file_path, "wb") as f:
                f.write(webp_content)
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save image file")

    # 5. Create DB Record
    # URL format: /media/products/{product_id}/{filename}
    # Note: frontend needs to prepend domain or use relative path.
    # We'll return the relative path.
    
    relative_url = f"/media/products/{product_id}/{filename}"
    
    new_image = ProductImage(
        product_id=product_id,
        url=relative_url,
        is_installation_photo=is_installation
    )
    
    session.add(new_image)
    
    # Also update main_image if it's empty
    if not product.main_image:
        product.main_image = relative_url
        session.add(product)
        
    await session.commit()
    await session.refresh(new_image)
    
    return {"url": relative_url, "id": new_image.id}
