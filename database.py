import sqlite3

DB_NAME = 'air_conditioners.db'

def init_db():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    brand TEXT NOT NULL,
                    model TEXT NOT NULL,
                    price INTEGER,
                    area INTEGER,
                    is_inverter INTEGER DEFAULT 0,
                    wifi_support INTEGER DEFAULT 0,
                    power_cooling REAL,
                    power_heating REAL,
                    image_url TEXT,
                    min_heat_temp INTEGER,
                    description TEXT
                )
            ''')
            conn.commit()
    except sqlite3.Error as e:
        print(f"Ошибка БД: {e}")

def add_product(brand, model, price, area, is_inverter, wifi_support, 
                power_cooling, power_heating, image_url, min_heat_temp, description):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO products (brand, model, price, area, is_inverter, wifi_support, 
                power_cooling, power_heating, image_url, min_heat_temp, description) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (brand, model, price, area, is_inverter, wifi_support, 
                  power_cooling, power_heating, image_url, min_heat_temp, description))
            conn.commit()
            return cursor.lastrowid
    except sqlite3.Error as e:
        print(f"Ошибка: {e}")
        return None

def get_all_products():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute('SELECT * FROM products')]

def get_products_by_area(area):
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM products WHERE area >= ? AND area <= ?', (area, area + 10))
        return [dict(row) for row in cursor.fetchall()]

# --- НОВЫЕ ФУНКЦИИ ---

def get_product_by_id(product_id):
    """Получает один товар по ID"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_product_field(product_id, field_name, new_value):
    """Обновляет конкретное поле товара"""
    # ВАЖНО: Проверка field_name, чтобы избежать SQL-инъекций
    allowed_fields = ['price', 'image_url', 'description', 'area']
    if field_name not in allowed_fields:
        return False

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # f-строка безопасна здесь, так как мы проверили field_name выше по белому списку
        cursor.execute(f'UPDATE products SET {field_name} = ? WHERE id = ?', (new_value, product_id))
        conn.commit()
        return True

def delete_product(product_id):
    """Удаляет товар"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
        conn.commit()

if __name__ == "__main__":
    init_db()