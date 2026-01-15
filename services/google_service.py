import os.path
from typing import Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Права доступа: Диск и Документы
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents'
]

SERVICE_ACCOUNT_FILE = 'credentials.json'

# --- ВСТАВЬТЕ СЮДА ВАШ ID ШАБЛОНА ---
TEMPLATE_DOC_ID = '1QNXCdMHiofUdHIi997R0fvq1ht-vcHkNi5fl3mTa4Zg' 

# ID Папки (куда сохраняем - создайте её на своем диске и расшарьте боту)
# Если оставить None, будет сохранять в корень "My Drive" робота (где 15 ГБ)
DESTINATION_FOLDER_ID = '1kLK6Vque3V5iPV1i1HjeH_su-TmyCzQt' 

class GoogleDocsService:
    def __init__(self):
        self.creds = None
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            self.creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
        else:
            raise FileNotFoundError(f"Файл {SERVICE_ACCOUNT_FILE} не найден!")

    def create_contract_from_template(self, title: str, replacements: Dict[str, str]) -> str:
        """
        1. Копирует шаблон.
        2. Делает замены текста.
        3. Возвращает ссылку на новый документ.
        """
        # Подключаемся к API
        drive_service = build('drive', 'v3', credentials=self.creds)
        docs_service = build('docs', 'v1', credentials=self.creds)

        # 1. Копируем файл шаблона
        copy_body = {'name': title}
        new_file = drive_service.files().copy(
            fileId=TEMPLATE_DOC_ID, 
            body=copy_body
        ).execute()
        
        new_doc_id = new_file.get('id')
        print(f"Created new doc: {new_doc_id}")

        # 2. Подготовка замен (Batch Update)
        requests = []
        for key, value in replacements.items():
            requests.append({
                'replaceAllText': {
                    'containsText': {
                        'text': key,
                        'matchCase': True
                    },
                    'replaceText': value or " " # Google не любит None
                }
            })

        # 3. Выполняем замены
        if requests:
            docs_service.documents().batchUpdate(
                documentId=new_doc_id, 
                body={'requests': requests}
            ).execute()
            
        # 4. Даем права на просмотр (чтобы вы могли открыть ссылку без входа под сервисным аккаунтом)
        # В идеале - шарить на ваш личный email. 
        # Но для простоты сделаем доступным "любому, у кого есть ссылка" (или шарьте на свой email).
        # drive_service.permissions().create(
        #     fileId=new_doc_id,
        #     body={'role': 'writer', 'type': 'user', 'emailAddress': 'ВАШ_EMAIL@gmail.com'}
        # ).execute()
        
        # Альтернатива (доступ по ссылке для чтения):
        drive_service.permissions().create(
            fileId=new_doc_id,
            body={'role': 'reader', 'type': 'anyone'}
        ).execute()

        return f"https://docs.google.com/document/d/{new_doc_id}/edit"

# Singleton instance
try:
    google_service = GoogleDocsService()
except Exception as e:
    print(f"Google Service Error: {e}")
    google_service = None