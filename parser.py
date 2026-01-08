import httpx
import re
import json
from bs4 import BeautifulSoup

async def parse_onliner_product(url: str):
    """
    Парсит данные товара с Onliner.by, используя API и HTML для спеков.
    """
    # 1. Извлекаем slug из URL
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
        # 2. Получаем HTML для парсинга таблицы характеристик
        html_resp = await client.get(url, headers=headers)
        if html_resp.status_code != 200:
            raise Exception(f"Ошибка загрузки страницы товара: {html_resp.status_code}")
        
        soup = BeautifulSoup(html_resp.text, 'html.parser')
        
        # 3. Пробуем API (SDAPI) для основных данных (цена, картинки)
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

        # --- Собираем данные ---
        product_data = {}
        
        # Основное из API (если доступно)
        product_data['title'] = data.get('full_name') or data.get('name') or soup.find('h1').get_text(strip=True)
        product_data['description'] = data.get('description', '')
        
        # Цена
        prices_data = data.get('prices')
        product_data['price'] = 0
        if prices_data and 'price_min' in prices_data:
             amount = prices_data['price_min'].get('amount')
             if amount:
                 product_data['price'] = int(float(amount))
        
        # Картинки
        product_data['main_image'] = data.get('images', {}).get('header', '')
        product_data['images'] = []
        
        # --- Парсинг таблицы характеристик через BeautifulSoup ---
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
                # Пропускаем заголовки групп (colspan=2)
                cells = row.find_all('td')
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True)
                    # Убираем текст подсказок (i-qmark)
                    for tip in cells[1].find_all(['span', 'div'], class_=['product-tip-wrapper', 'i-tip']):
                        tip.decompose()
                    
                    value = cells[1].get_text(strip=True).replace('\xa0', ' ')
                    all_specs[key] = value
                    
                    # Извлекаем целевые поля
                    if 'Мощность охлаждения' in key:
                        match = re.search(r'([\d\.]+)', value)
                        if match: target_specs['power_cooling'] = float(match.group(1))
                    
                    elif 'Мощность обогрева' in key:
                        match = re.search(r'([\d\.]+)', value)
                        if match: target_specs['power_heating'] = float(match.group(1))
                    
                    elif 'Обслуживаемая площадь' in key:
                        match = re.search(r'(\d+)', value)
                        if match: target_specs['area'] = int(match.group(1))
                        
                    elif 'Инверторная технология' in key:
                        target_specs['is_inverter'] = True
                        categories.append("Инвертор")
                    
                    elif 'Тип внутреннего блока' in key and 'настенный' in value.lower():
                        categories.append("Настенный")

        # Если площадь не нашли в табл, пробуем старую эвристику
        if target_specs['area'] == 0:
            btu_map = {'07': 20, '09': 25, '12': 35, '18': 50, '24': 70}
            for k, v in btu_map.items():
                if k in slug or k in product_data['title']:
                    target_specs['area'] = v
                    break

        product_data['specs'] = all_specs or target_specs # Сохраняем все или только целевые
        # Добавляем целевые прямо в specs для удобства бота, если они были найдены
        product_data['specs'].update({k: v for k, v in target_specs.items() if v is not None})
        
        product_data['categories'] = list(set(categories))
        product_data['area'] = target_specs['area']

        return product_data

if __name__ == "__main__":
    import asyncio
    
    async def debug_main():
        url = "https://catalog.onliner.by/conditioners/mdv/mdsalf12hrfn8mdo"
        try:
             res = await parse_onliner_product(url)
             print(json.dumps(res, indent=4, ensure_ascii=False))
        except Exception as e:
            print(f"Error in parse_onliner_product: {e}")

    asyncio.run(debug_main())

