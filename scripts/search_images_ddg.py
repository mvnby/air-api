import asyncio
import sys
import logging
import argparse
import time
import requests
from io import BytesIO
from pathlib import Path
from PIL import Image
from duckduckgo_search import DDGS
from sqlmodel import select

# Extend path to include project root
sys.path.append(str(Path(__file__).parent.parent))

from core.database import async_session_maker
from models import Product

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

MIN_WIDTH = 800
MIN_HEIGHT = 600

def search_hq_image(query: str) -> str | None:
    """
    Searches for a high-quality image using DuckDuckGo.
    Returns the URL of the best candidate or None.
    """
    try:
        with DDGS() as ddgs:
            # Expanded search to ensure we get product shots
            # Adding "air conditioner" or similar might help context if title is obscure,
            # but usually product titles are specific enough.
            # We filter by size directly in the query parameters if possible, 
            # but ddg python lib handles it via 'size' param (Large, Wallpaper, etc) or we allow all and filter manually.
            # 'size="Large"' defaults to finding bigger images.
            
            results = ddgs.images(
                keywords=query,
                region="wt-wt",
                safesearch="off",
                size="Large", # Request large images
                max_results=5
            )
            
            for res in results:
                image_url = res.get('image')
                width = res.get('width', 0)
                height = res.get('height', 0)
                
                # Check dimensions if available from API
                if width and height:
                    if width < MIN_WIDTH or height < MIN_HEIGHT:
                        continue
                
                # Basic domain filtering
                if "vector" in image_url or "icon" in image_url or "logo" in image_url:
                    continue
                    
                return image_url
                
    except Exception as e:
        logger.error(f"  Search error for '{query}': {e}")
        
    return None

async def process_products(dry_run: bool = False):
    async with async_session_maker() as session:
        # Fetch all products, prioritize published
        stmt = select(Product).order_by(Product.is_published.desc())
        result = await session.execute(stmt)
        products = result.scalars().all()
        
        logger.info(f"Found {len(products)} products to process. Dry Run: {dry_run}")
        
        updated_count = 0
        
        for product in products:
            if not product.main_image:
                continue
            
            # Identify local path
            db_path = product.main_image.lstrip("/")
            abs_path = Path.cwd() / db_path
            
            # Check if we should skip? 
            # We want to overwrite EVERYTHING with better versions, 
            # assuming current ones are bad (as per user context).
            
            logger.info(f"Processing: {product.title}")
            
            # 1. Search
            # Clean title for search (remove internal codes if any?)
            # Usually title is good: "MDV MDSAG-07HRN1"
            query = f"{product.title} кондиционер"
            
            # Rate limit protection
            time.sleep(6)
            
            best_url = search_hq_image(query)
            
            if best_url:
                logger.info(f"  Found candidate: {best_url}")
                
                 # 2. Download and Validate
                if not dry_run:
                    try:
                        img_resp = requests.get(best_url, headers=HEADERS, timeout=10)
                        if img_resp.status_code == 200:
                            img = Image.open(BytesIO(img_resp.content))
                            
                            # Double check size (sometimes metadata lies)
                            if img.width < MIN_WIDTH or img.height < MIN_HEIGHT:
                                logger.warning(f"  Skipping: Real size {img.width}x{img.height} too small")
                                continue
                                
                            # Convert/Save
                            abs_path.parent.mkdir(parents=True, exist_ok=True)
                            
                            # Preserve aspect ratio, convert to webp
                            img.save(abs_path, "WEBP", quality=90)
                            logger.info(f"  Overwritten {abs_path.name}")
                            updated_count += 1
                        else:
                            logger.warning(f"  Failed download: {img_resp.status_code}")
                    except Exception as e:
                        logger.error(f"  Download error: {e}")
            else:
                logger.warning("  No suitable image found.")
                
        logger.info(f"Finished. Updated {updated_count} images.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Search without saving files")
    args = parser.parse_args()
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(process_products(dry_run=args.dry_run))
