import csv
import os
from database import add_product, init_db

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
        # DictReader автоматически использует первую строку как заголовки
        reader = csv.DictReader(file)
        
        count = 0
        for row in reader:
            # Преобразуем данные из строк в нужные типы
            brand = row.get('brand', 'Unknown')
            model = row.get('model', 'Unknown')
            price = clean_price(row.get('price'))
            area = int(row.get('area', 20))
            
            # Конвертируем 'да'/'нет' или '1'/'0' в число
            is_inverter = 1 if row.get('is_inverter', '').lower() in ['да', '1', 'true', 'yes'] else 0
            wifi_support = 1 if row.get('wifi_support', '').lower() in ['да', '1', 'true', 'yes'] else 0
            
            power_cooling = float(row.get('power_cooling', 0) or 0)
            power_heating = float(row.get('power_heating', 0) or 0)
            min_heat_temp = int(row.get('min_heat_temp', -5) or -5)
            
            image_url = row.get('image_url', '')
            description = row.get('description', '')

            # Добавляем в базу
            add_product(
                brand, model, price, area, is_inverter, wifi_support,
                power_cooling, power_heating, image_url, min_heat_temp, description
            )
            count += 1

    print(f"\n✅ Импорт завершен! Добавлено товаров: {count}")

if __name__ == "__main__":
    import_from_csv()