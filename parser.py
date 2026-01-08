import httpx
import re
import json

async def parse_onliner_product(url: str):
    """
    Парсит данные товара с Onliner.by.
    """
    # 1. Извлекаем slug из URL
    # Пример: https://catalog.onliner.by/conditioners/mdv/mdsalf12hrfn8mdo -> mdsalf12hrfn8mdo
    match = re.search(r'Catalog\.onliner\.by/.*?/([^/]+)$', url, re.IGNORECASE)
    if not match:
         match = re.search(r'/([^/]+)$', url)
    
    if not match:
        raise ValueError("Не удалось извлечь ID товара из ссылки")
    
    slug = match.group(1)
    
    # 2. Пробуем API (SDAPI)
    # Обычно доступно по: https://catalog.api.onliner.by/products/{slug}
    # Но нужен корректный Host и User-Agent
    api_url = f"https://catalog.api.onliner.by/products/{slug}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://catalog.onliner.by",
        "Referer": url
    }
    
    async with httpx.AsyncClient() as client:
        # Получаем основную инфу
        resp = await client.get(api_url, headers=headers)
        
        if resp.status_code != 200:
            # Fallback: пробуем другой эндпоинт, который использует мобильное приложение или сам сайт
            # https://catalog.onliner.by/sdapi/catalog.api/products/{slug}
            api_url_v2 = f"https://catalog.onliner.by/sdapi/catalog.api/products/{slug}"
            resp = await client.get(api_url_v2, headers=headers)
            
            if resp.status_code != 200:
                raise Exception(f"Ошибка доступа к Onliner API: {resp.status_code}")

        data = resp.json()
        
        # 3. Формируем словарь Product
        product_data = {}
        
        # Название
        product_data['title'] = data.get('full_name') or data.get('name')
        product_data['description'] = data.get('description', '')
        
        # Цена (минимальная)
        prices = data.get('prices', {})
        product_data['price'] = 0
        if prices:
            product_data['price'] = int(float(prices.get('min', 0)) * 100) # конвертация? нет, там обычно просто число
            # В API цены могут быть в BYN * 10000 или что-то такое, надо проверить.
            # Обычно prices.min это float в BYN.
            product_data['price'] = int(float(prices.get('min', 0))) # Берем целую часть
            
        # Картинки
        # В images -> header (главная) и icon.
        # Могут быть photos отдельно.
        product_data['main_image'] = data.get('images', {}).get('header', '')
        
        # Для галереи нужны дополнительные запросы или search в image fields
        # В базовом ответе часто нет всех фото. Но пока возьмем, что есть.
        product_data['images'] = []
        
        # Характеристики (specs)
        # Они часто лежат в другом эндпоинте: /products/{slug}/specs
        # Но для простоты пока оставим пустым или попробуем достать.
        product_data['specs'] = {}
        
        # 4. Дополнительный запрос за характеристиками (если нужно)
        # specs_url = f"https://catalog.api.onliner.by/products/{slug}/specs"
        # resp_specs = await client.get(specs_url, headers=headers)
        # if resp_specs.status_code == 200:
        #    ...
        
        # Категории (извлечем из description или specs)
        product_data['categories'] = []
        if "инвертор" in product_data.get('description', '').lower():
             product_data['categories'].append("Инвертор")
             
        # Площадь (надо парсить из описания или названия)
        # Пример: MDSALF-12... -> часто цифра 12 = 12000 BTU ~ 35м2
        # Это сложная эвристика, пока оставим 0 или дефолт.
        product_data['area'] = 0
        btu_map = {'07': 20, '09': 25, '12': 35, '18': 50, '24': 70}
        for k, v in btu_map.items():
            if k in slug or k in product_data['title']:
                product_data['area'] = v
                break

        return product_data

# Тест запуска
if __name__ == "__main__":
    import asyncio
    url = "https://catalog.onliner.by/conditioners/mdv/mdsalf12hrfn8mdo"
    try:
        res = asyncio.run(parse_onliner_product(url))
        print(json.dumps(res, indent=4, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}")
