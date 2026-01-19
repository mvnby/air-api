import sqlite3

DB_PATH = "air_conditioners.db"

MAPPING = {
    "Новый лид": "new_lead",
    "Замер/Осмотр": "assessment",
    "КП отправлено": "proposal",
    "Переговоры": "negotiation",
    "Отложено": "deferred",
    "Предоплата получена": "won_deposit",
    "Монтаж": "installation",
    "Закрыто": "completed",
    "Отмена": "canceled",
    # Legacy fallbacks just in case
    "proposal_sent": "proposal"
}

def migrate_db():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check current values
        cursor.execute('SELECT status, COUNT(*) FROM "order" GROUP BY status')
        print("Before migration:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")
            
        print("\nMigrating...")
        for ru, en in MAPPING.items():
            cursor.execute('UPDATE "order" SET status = ? WHERE status = ?', (en, ru))
            if cursor.rowcount > 0:
                print(f"  Updated {cursor.rowcount} rows: '{ru}' -> '{en}'")
                
        conn.commit()
        
        # Check result
        cursor.execute('SELECT status, COUNT(*) FROM "order" GROUP BY status')
        print("\nAfter migration:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")
            
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_db()
