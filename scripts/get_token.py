import os
import sys

# Добавляем путь к корню проекта для корректных импортов (если понадобятся)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_auth_oauthlib.flow import InstalledAppFlow

# Права: полный доступ к Диску и Документам
# Это позволит боту создавать файлы от вашего имени
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets'
]

def main():
    # Проверка наличия файла секрета
    if not os.path.exists('client_secret.json'):
        print("❌ Ошибка: Файл client_secret.json не найден в корне проекта!")
        print("Скачайте его из Google Cloud Console -> Credentials -> OAuth 2.0 Client IDs")
        return

    # Запуск процесса авторизации
    flow = InstalledAppFlow.from_client_secrets_file(
        'client_secret.json', SCOPES
    )
    
    print("🌍 Сейчас откроется браузер (или ссылка в консоли).")
    print("Войдите в свой аккаунт Google (тот, который вы добавили в Test Users).")
    print("Если увидите экран 'Google hasn’t verified this app' -> нажмите Advanced -> Go to AirBot (unsafe).")
    
    # port=0 выберет свободный порт автоматически
    creds = flow.run_local_server(port=0)
    
    # Сохраняем полученный токен доступа
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
    
    print("\n✅ Успешно! Файл token.json создан.")
    print("Теперь бот имеет доступ к вашему Диску и будет использовать вашу квоту.")

if __name__ == '__main__':
    main()