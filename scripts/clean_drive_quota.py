# scripts/clean_drive_quota.py
import os
import sys

# Добавляем путь к корню проекта, чтобы импорты работали
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.google_service import get_google_service, SCOPES
from googleapiclient.discovery import build

def clean_drive():
    if not get_google_service():
        print("❌ Ошибка: Google Service не инициализирован. Проверьте credentials.json")
        return

    # Подключаемся к API напрямую, так как get_google_service() - это обертка
    creds = get_google_service().creds
    service = build('drive', 'v3', credentials=creds)

    print("🔍 Проверка квоты сервисного аккаунта...")
    about = service.about().get(fields="storageQuota").execute()
    quota = about['storageQuota']
    usage_gb = int(quota['usage']) / (1024**3)
    limit_gb = int(quota['limit']) / (1024**3)
    print(f"📊 Использовано: {usage_gb:.2f} ГБ из {limit_gb:.2f} ГБ")

    # 1. Очистка корзины
    print("🗑 Очистка корзины...")
    try:
        service.files().emptyTrash().execute()
        print("✅ Корзина очищена.")
    except Exception as e:
        print(f"⚠️ Ошибка очистки корзины: {e}")

    # 2. Поиск файлов для удаления (опционально)
    # Например, удалим все файлы с "Договор" в названии, созданные этим аккаунтом
    # ВНИМАНИЕ: Это удалит файлы безвозвратно!
    print("🔎 Поиск старых файлов (contracts)...")
    results = service.files().list(
        q="name contains 'Договор' and trashed = false",
        fields="nextPageToken, files(id, name, size)"
    ).execute()
    items = results.get('files', [])

    if not items:
        print("Нет файлов для удаления.")
    else:
        print(f"Найдено файлов: {len(items)}")
        confirm = input("❗ Удалить эти файлы? (y/n): ")
        if confirm.lower() == 'y':
            for item in items:
                try:
                    service.files().delete(fileId=item['id']).execute()
                    print(f"❌ Удален: {item['name']} ({item.get('size', 0)} байт)")
                except Exception as e:
                    print(f"Ошибка удаления {item['name']}: {e}")

if __name__ == "__main__":
    clean_drive()