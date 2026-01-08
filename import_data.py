import csv
import os
from sqlmodel import Session
from database import engine, init_db
from models import Product

# Имя файла с данными (должен лежать рядом со скриптом)
CSV_FILENAME = 'products.csv'

def clean_price(price_str):
    """Превращает '1 200,00 р.' в число 1200"""
    if not price_str:
        return 0
    # Удаляем пробелы, 'р.', заменяем запятую на точку
    clean = price_str.replace('р.', '').replace(' ', '').replace(',', '.')
    # Удаляем неразрывные пробелы (частая проблема при копировании)
    clean = clean.replace('\xa0', '')
    try:
        return int(float(clean))
    except ValueError:
        return 0

def import_from_csv():
    if not os.path.exists(CSV_FILENAME):
        print(f"Файл {CSV_FILENAME} не найден! Создайте его.")
        return

    print(f"Начинаем импорт из {CSV_FILENAME}...")
    
    # Убедимся, что база существует
    init_db()

    with open(CSV_FILENAME, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        with Session(engine) as session:
            count = 0
            for row in reader:
                brand = row.get('brand', 'Unknown')
                model = row.get('model', 'Unknown')
                title = f"{brand} {model}"
                
                price = clean_price(row.get('price'))
                area = int(row.get('area', 20))
                
                is_inverter = row.get('is_inverter', '').lower() in ['да', '1', 'true', 'yes']
                wifi_support = row.get('wifi_support', '').lower() in ['да', '1', 'true', 'yes']
                
                power_cooling = float(row.get('power_cooling', 0) or 0)
                power_heating = float(row.get('power_heating', 0) or 0)
                min_heat_temp = int(row.get('min_heat_temp', -5) or -5)
                
                main_image = row.get('image_url', '')
                description = row.get('description', '')

                specs = {
                    "brand": brand,
                    "model": model,
                    "power_cooling": power_cooling,
                    "power_heating": power_heating,
                    "min_heat_temp": min_heat_temp,
                    "wifi": wifi_support
                }
                
                categories = []
                if is_inverter:
                    categories.append("Инвертор")

                product = Product(
                    title=title,
                    description=description,
                    price=price,
                    area=area,
                    main_image=main_image,
                    categories=categories,
                    specs=specs,
                    is_published=True
                )
                
                session.add(product)
                count += 1
            
            session.commit()

    print(f"\n✅ Импорт завершен! Добавлено товаров: {count}")

if __name__ == "__main__":
    import_from_csv()