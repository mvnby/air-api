import os.path
from typing import Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Права доступа
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents'
]

# Файлы авторизации
TOKEN_FILE = 'token.json'             # Генерируется скриптом scripts/get_token.py
CLIENT_SECRET_FILE = 'client_secret.json' # Скачивается из Google Cloud Console

# ID Шаблона (Ваш существующий шаблон)
TEMPLATE_DOC_ID = '1QNXCdMHiofUdHIi997R0fvq1ht-vcHkNi5fl3mTa4Zg' 

# ID Папки назначения
# Файлы будут создаваться в этой папке на ВАШЕМ диске.
DESTINATION_FOLDER_ID = '1kLK6Vque3V5iPV1i1HjeH_su-TmyCzQt' 

class GoogleDocsService:
    def __init__(self):
        self.creds = None
        self._authenticate()

    def _authenticate(self):
        """
        Автоматическая аутентификация через token.json.
        Если токен истек, пытается обновить его.
        """
        # 1. Пытаемся загрузить существующий токен
        if os.path.exists(TOKEN_FILE):
            try:
                self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            except Exception as e:
                print(f"Ошибка чтения токена: {e}")
                self.creds = None
        
        # 2. Если токена нет или он протух - обновляем
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    print("Обновление Google токена...")
                    self.creds.refresh(Request())
                    # Сохраняем обновленный токен
                    with open(TOKEN_FILE, 'w') as token:
                        token.write(self.creds.to_json())
                except Exception as e:
                    print(f"Не удалось обновить токен: {e}")
                    self.creds = None

            # Если все еще нет прав (и нет рефреш токена), то нужна ручная авторизация
            if not self.creds:
                print("⚠️ Внимание: Требуется авторизация Google!")
                print("Запустите локально: python scripts/get_token.py")
                # Мы не можем запустить интерактивный вход на сервере без браузера,
                # поэтому оставляем self.creds = None. Методы будут возвращать ошибку.

    def create_contract_from_template(self, title: str, replacements: Dict[str, str]) -> str:
        """
        Создает договор, копируя шаблон и заменяя текст.
        Использует права владельца (Вас).
        """
        # Повторная проверка перед выполнением операции
        if not self.creds or not self.creds.valid:
            # Пытаемся еще раз (вдруг токен обновился)
            self._authenticate()
            if not self.creds or not self.creds.valid:
                return "Ошибка: Нет доступа к Google API. Запустите scripts/get_token.py"

        try:
            drive_service = build('drive', 'v3', credentials=self.creds)
            docs_service = build('docs', 'v1', credentials=self.creds)

            # 1. Копируем файл шаблона в нужную папку
            # parents=['ID'] заставляет файл появиться именно в этой папке
            copy_body = {
                'name': title,
                'parents': [DESTINATION_FOLDER_ID] if DESTINATION_FOLDER_ID else []
            }
            
            new_file = drive_service.files().copy(
                fileId=TEMPLATE_DOC_ID, 
                body=copy_body
            ).execute()
            
            new_doc_id = new_file.get('id')
            print(f"Created new doc: {new_doc_id}")

            # 2. Подготовка замен (Batch Update)
            requests = []
            for key, value in replacements.items():
                # Защита от None, чтобы API не ругался
                safe_val = str(value) if value is not None else " "
                requests.append({
                    'replaceAllText': {
                        'containsText': {
                            'text': key,
                            'matchCase': True
                        },
                        'replaceText': safe_val
                    }
                })

            # 3. Выполняем замены
            if requests:
                docs_service.documents().batchUpdate(
                    documentId=new_doc_id, 
                    body={'requests': requests}
                ).execute()

            # Права выдавать не нужно, так как файл и так Ваш!
            return f"https://docs.google.com/document/d/{new_doc_id}/edit"
            
        except Exception as e:
            error_msg = str(e)
            print(f"Google API Error: {error_msg}")
            if "quota" in error_msg.lower():
                return "Ошибка: Превышена квота Google API (Storage Quota)."
            return f"Ошибка Google API: {error_msg}"

# Singleton instance
try:
    google_service = GoogleDocsService()
except Exception as e:
    print(f"Google Service Init Error: {e}")
    google_service = None