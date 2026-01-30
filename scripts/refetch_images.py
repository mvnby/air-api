import asyncio
import re
import sys
import logging
import requests
import base64
from PIL import Image
from io import BytesIO
from pathlib import Path
from sqlmodel import select

# Extend path to include project root
sys.path.append(str(Path(__file__).parent.parent))

from core.database import async_session_maker
from models import Product

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def get_headers(referer: str) -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://catalog.onliner.by",
        "Referer": referer,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8"
    }

def decode_imgproxy_url(url: str) -> str | None:
    markers = ["aHR0cHM", "aHR0cD"]
    for marker in markers:
        if marker in url:
            try:
                start_idx = url.find(marker)
                tail = url[start_idx:]
                clean_tail = tail.replace('/', '')
                missing_padding = len(clean_tail) % 4
                if missing_padding:
                    clean_tail += '=' * (4 - missing_padding)
                
                decoded_bytes = base64.urlsafe_b64decode(clean_tail)
                decoded_str = decoded_bytes.decode('utf-8')
                if decoded_str.startswith('http'):
                    return decoded_str
            except Exception:
                pass
    return None

def is_generic(url: str) -> bool:
    if "gc.onliner.by" in url: return True
    if "na_kazdyj_den" in url: return True
    return False

def find_best_candidates(html_text: str) -> list[str]:
    # Pattern to match both standard and escaped URLs
    pattern = r'(https?:(?:/|\\/){2}(?:imgproxy|content)\.onliner\.by[a-zA-Z0-9\-_:/\.=%\\]+)'
    raw_matches = re.findall(pattern, html_text)
    
    unique_matches = set()
    content_urls = []
    imgproxy_urls = []
    
    for url in raw_matches:
        url = url.replace('\\/', '/')
        if url in unique_matches: continue
        unique_matches.add(url)
        
        if is_generic(url): continue

        if "content.onliner.by" in url:
             content_urls.append(url)
        elif "imgproxy.onliner.by" in url:
             imgproxy_urls.append(url)
             # Try to decode child
             decoded = decode_imgproxy_url(url)
             if decoded and not is_generic(decoded):
                 if decoded not in unique_matches:
                      content_urls.append(decoded)
                      unique_matches.add(decoded)

    # Sort imgproxy by size (width)
    def get_width(u):
        m = re.search(r'w:(\d+)', u)
        return int(m.group(1)) if m else 0
    
    imgproxy_urls.sort(key=get_width, reverse=True)
    
    # Prioritize: content URLs first, then imgproxy (largest first)
    final = []
    seen = set()
    for u in content_urls + imgproxy_urls:
         if u not in seen:
              final.append(u)
              seen.add(u)
              
    return final

async def refetch_images():
    async with async_session_maker() as session:
        stmt = select(Product).where(Product.source_url != None).where(Product.source_url != "")
        stmt = stmt.order_by(Product.is_published.desc())
        
        result = await session.execute(stmt)
        products = result.scalars().all()
        
        logger.info(f"Found {len(products)} products with source_url.")
        
        count_updated = 0
        
        for product in products:
            if not product.main_image:
                continue
            
            db_path = product.main_image.lstrip("/")
            abs_path = Path.cwd() / db_path
            
            logger.info(f"Refetching {product.slug}...")
            
            try:
                # Use source_url as referer for the main request too (sometimes helps)
                resp = requests.get(product.source_url, headers=get_headers(product.source_url), timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"  Source page error {resp.status_code}")
                    continue
                
                candidates = find_best_candidates(resp.text)
                
                success = False
                for url in candidates:
                    try:
                        # Use source_url as referer for image download
                        img_resp = requests.get(url, headers=get_headers(product.source_url), timeout=10)
                        
                        if img_resp.status_code == 200:
                            img = Image.open(BytesIO(img_resp.content))
                            abs_path.parent.mkdir(parents=True, exist_ok=True)
                            img.save(abs_path, "WEBP", quality=90)
                            
                            logger.info(f"  Overwriting {abs_path.name} with {url}")
                            count_updated += 1
                            success = True
                            break # Move to next product on success
                        else:
                            # logger.warning(f"  Failed {url}: {img_resp.status_code}")
                            pass
                    except Exception:
                        pass
                
                if not success:
                    logger.warning("  No suitable image downloaded.")
                    
            except Exception as e:
                logger.error(f"  Error refetching {product.slug}: {e}")
                
        logger.info(f"Refetch complete. Updated {count_updated} images.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(refetch_images())
