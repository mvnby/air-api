import httpx
import re
from bs4 import BeautifulSoup
from typing import Dict, Any
from .base import BaseParser

class OnlinerParser(BaseParser):
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
                        key = cells[0].get_text(strip=True)
                        # Check for boolean icons
                        icon_true = cells[1].find('span', class_='i-tip')
                        icon_false = cells[1].find('span', class_='i-x')
                        
                        value = ""
                        if icon_true:
                            value = "да"
                        elif icon_false:
                            value = "нет"
                        else:
                            # Remove tooltips (BUT do not remove i-tip if we hadn't checked it yet, logic above handles it)
                            # safe to strict decompose wrapper now
                            for tip in cells[1].find_all(['span', 'div'], class_='product-tip-wrapper'):
                                tip.decompose()
                            value = cells[1].get_text(strip=True).replace('\xa0', ' ')
                        
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
                                min_temp = int(match.group(1))
                                # Only add winter tags for temperatures -15 and below
                                if min_temp <= -15:
                                    # Normalize to nearest supported slug: 15, 20, 25, 30
                                    # If it's -22, it stays -20 (downwards compatibility)
                                    # But since user specifically mentioned winter-15, winter-20 etc, 
                                    # we check thresholds. 
                                    if min_temp <= -30: tag_slug = "winter-30"
                                    elif min_temp <= -25: tag_slug = "winter-25"
                                    elif min_temp <= -20: tag_slug = "winter-20"
                                    else: tag_slug = "winter-15"
                                    
                                    # We add the slug to categories so the importer_service can resolve it to a Tag
                                    if tag_slug not in categories:
                                        categories.append(tag_slug)

            # Use parsed Area if available, else 0
            product_data['area'] = target_specs['area']
            
            # Auto-categories
            if target_specs['area']:
                categories.append(f"до {target_specs['area']} м²")
            
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
            
            # Related products discovery
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
            
            return product_data
