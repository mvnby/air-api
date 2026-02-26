import httpx
import re
from bs4 import BeautifulSoup
from typing import Dict, Any
from .base import BaseParser

class OnlinerParser(BaseParser):
    @staticmethod
    def _extract_spec_value(cell) -> str:
        # Onliner uses icon-only values for boolean fields:
        # <span class="i-tip"></span> -> yes, <span class="i-x"></span> -> no.
        has_true_icon = bool(
            cell.find(
                lambda tag: tag.has_attr("class") and "i-tip" in tag.get("class", [])
            )
        )
        if has_true_icon:
            return "да"

        has_false_icon = bool(
            cell.find(
                lambda tag: tag.has_attr("class") and "i-x" in tag.get("class", [])
            )
        )
        if has_false_icon:
            return "нет"

        for tip in cell.find_all(['span', 'div'], class_='product-tip-wrapper'):
            tip.decompose()
        return cell.get_text(" ", strip=True).replace('\xa0', ' ')

    def supports(self, url: str) -> bool:
        return "catalog.onliner.by" in url or "catalog.api.onliner.by" in url

    async def parse(self, url: str) -> Dict[str, Any]:
        """
        Parses product data from Onliner.by using API and HTML scrapping for specs.
        """
        # 1. Extract slug
        match = re.search(r'Catalog\.onliner\.by/.*?/([^/]+)$', url, re.IGNORECASE)
        if not match:
             match = re.search(r'/([^/]+)$', url)
        
        if not match:
            raise ValueError("Не удалось извлечь ID товара из ссылки")
        
        slug = match.group(1)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": "https://catalog.onliner.by",
            "Referer": url
        }
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # 2. Get HTML for specs table
            html_resp = await client.get(url, headers=headers)
            if html_resp.status_code != 200:
                raise Exception(f"Ошибка загрузки страницы товара: {html_resp.status_code}")
            
            soup = BeautifulSoup(html_resp.text, 'html.parser')
            
            # 3. Try API for main data
            api_url = f"https://catalog.api.onliner.by/products/{slug}"
            api_resp = await client.get(api_url, headers=headers)
            
            data = {}
            if api_resp.status_code == 200:
                data = api_resp.json()
            else:
                # Fallback API
                api_url_v2 = f"https://catalog.onliner.by/sdapi/catalog.api/products/{slug}"
                api_resp = await client.get(api_url_v2, headers=headers)
                if api_resp.status_code == 200:
                    data = api_resp.json()

            # --- Assemble Data ---
            product_data = {}
            
            # Basic info from API (or fallback to HTML H1)
            product_data['title'] = data.get('full_name') or data.get('name') or soup.find('h1').get_text(strip=True)
            product_data['description'] = data.get('description', '')
            
            # Price
            prices_data = data.get('prices')
            product_data['price'] = 0
            if prices_data and 'price_min' in prices_data:
                 amount = prices_data['price_min'].get('amount')
                 if amount:
                     product_data['price'] = int(float(amount))
            
            # Images
            product_data['main_image'] = data.get('images', {}).get('header', '')
            product_data['images'] = [] # Could extend to fetch more images
            
            # Specs parsing from HTML
            all_specs = {}
            target_specs = {
                'power_cooling': None,
                'power_heating': None,
                'area': 0,
                'is_inverter': False
            }
            categories = []
            
            specs_table = soup.find('table', class_='product-specs__table')
            if specs_table:
                rows = specs_table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) == 2:
                        key = cells[0].get_text(" ", strip=True).replace('\xa0', ' ')
                        value = self._extract_spec_value(cells[1])
                        
                        all_specs[key] = value
                        
                        # Extract target fields logic
                        if 'Мощность охлаждения' in key:
                            match = re.search(r'([\d\.]+)', value)
                            if match: target_specs['power_cooling'] = float(match.group(1))
                        
                        elif 'Мощность обогрева' in key:
                            match = re.search(r'([\d\.]+)', value)
                            if match: target_specs['power_heating'] = float(match.group(1))
                        
                        elif 'Площадь помещения' in key or 'Обслуживаемая площадь' in key:
                            match = re.search(r'(\d+)', value)
                            if match and not target_specs['area']: # Only if not set (or use priority)
                                target_specs['area'] = int(match.group(1))
                        
                        elif 'Инверторная технология' in key:
                            if 'да' in value.lower():
                                target_specs['is_inverter'] = True
                        
                        elif 'Минимальная температура' in key or 'Рабочая температура при обогреве' in key:
                            # Usually format is "от -20 до +24 °C"
                            match = re.search(r'(-\d+)', value)
                            if match:
                                target_specs['min_temp_heating'] = int(match.group(1))

            # Use parsed Area if available, else 0
            product_data['area'] = target_specs['area']
            
            # Auto-categories (Area tags are now handled by slug in ImporterService)
            # Add brand from title (simple heuristic)
            # manufacturer
            manufacturer = data.get('manufacturer', {}).get('name')
            if not manufacturer:
                 # heuristic fallback
                 parts = title.split()
                 if len(parts) > 0:
                     if parts[0].lower() in ['кондиционер', 'сплит-система']:
                         if len(parts) > 1: manufacturer = parts[1]
                     else:
                         manufacturer = parts[0]
            
            if manufacturer:
                categories.append(manufacturer)

            product_data['categories'] = categories
            product_data['specs'] = all_specs
            # Expose raw metrics for auto-tagging
            product_data['metrics'] = target_specs
            
            # 3. Extract gallery images from HTML directly
            # User pointed out that images are in .swiper-slide elements within the gallery
            gallery_thumbs = soup.select('.product-gallery__thumb img')
            for img in gallery_thumbs:
                src = img.get('src') or img.get('data-src')
                if src:
                    # Clean up URL (sometimes has size params)
                    # ex: https://imgproxy.onliner.by/..../w:200/h:200/ex:1/f:jpg/...
                    # We might want to try to get the original or larger version.
                    # Usually Onliner imgproxy URLs contain encoded original URL or params.
                    # But often sticking to what's there or just removing resizing params might work.
                    # Actually, if we look at the HTML from the user:
                    # src="https://imgproxy.onliner.by/E-nW46.../w:200/h:200/ex:1/f:jpg/..."
                    # The high-res is usually loaded on click.
                    # But the NUXT data showed "main" and "retina" variants.
                    
                    # For now, let's just collect these URLs. 
                    # If they are thumbnails, we might want to try to remove resizing?
                    # Onliner imgproxy format: /.../w:200/h:200/...
                    # If we remove /w:200/h:200 from URL, does it give full size? 
                    # Often not, it depends on signature.
                    
                    # NOTE: Emulating what the browser sees.
                    if src not in product_data['images'] and src != product_data['main_image']:
                         product_data['images'].append(src)

            # Also try to fallback to NUXT regex if HTML extraction yields nothing or low quality
            # (Keeping the regex as backup or for better quality URLs if needed, but simplifying)
            if not product_data['images']:
                 try:
                    for script in soup.find_all('script'):
                        if script.string and 'window.__NUXT__' in script.string:
                            # Simple regex for all image-like URLs
                            # "https://...onliner.by/...jpg"
                            urls = re.findall(r'"(https://[^"]+(?:content|imgproxy)\.onliner\.by[^"]+)"', script.string)
                            for u in urls:
                                u = u.replace(r'\/', '/')
                                # Filter out likely irrelevant icons/assets
                                if u not in product_data['images'] and u != product_data['main_image']:
                                    # Heuristic: product images usually long hash or specific path
                                    if 'catalog/device' in u or 'imgproxy' in u:
                                         product_data['images'].append(u)
                            break
                 except Exception:
                     pass
            
            # Legacy fallback: Related products discovery
            related_urls = []
            related_links = soup.select('a.offers-description-filter-control')
            for link in related_links:
                href = link.get('href')
                if href:
                    if href.startswith('/'):
                        href = f"https://catalog.onliner.by{href}"
                    if href not in related_urls and href != url:
                        related_urls.append(href)

            product_data['related_urls'] = related_urls
            product_data['slug'] = slug
            
            return product_data
