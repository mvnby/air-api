import os.path
from typing import Dict, Any, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Права доступа
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents'
]

TOKEN_FILE = 'token.json'
DESTINATION_FOLDER_ID = '1kLK6Vque3V5iPV1i1HjeH_su-TmyCzQt' 

class GoogleDocsService:
    def __init__(self):
        self.creds = None
        self._authenticate()

    def _authenticate(self):
        if os.path.exists(TOKEN_FILE):
            try:
                self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            except Exception:
                self.creds = None
        
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    with open(TOKEN_FILE, 'w') as token:
                        token.write(self.creds.to_json())
                except Exception:
                    self.creds = None

    def generate_doc(self, template_id: str, title: str, replacements: Dict[str, str], table_data: Optional[List[List[str]]] = None) -> str:
        """
        Универсальный метод генерации документа.
        """
        if not self.creds or not self.creds.valid:
            self._authenticate()
            if not self.creds: return "Ошибка: Нет доступа к Google API (проверьте token.json)."

        try:
            drive_service = build('drive', 'v3', credentials=self.creds)
            docs_service = build('docs', 'v1', credentials=self.creds)

            # 1. Копируем файл шаблона
            copy_body = {
                'name': title,
                'parents': [DESTINATION_FOLDER_ID] if DESTINATION_FOLDER_ID else []
            }
            try:
                new_file = drive_service.files().copy(fileId=template_id, body=copy_body).execute()
            except Exception as e:
                return f"Ошибка копирования шаблона (проверьте ID шаблона): {e}"
                
            new_doc_id = new_file.get('id')

            # 2. Выполняем простые текстовые замены (Batch Update)
            requests = []
            for key, value in replacements.items():
                safe_val = str(value) if value is not None else ""
                requests.append({
                    'replaceAllText': {
                        'containsText': {'text': key, 'matchCase': True},
                        'replaceText': safe_val
                    }
                })
            
            if requests:
                docs_service.documents().batchUpdate(documentId=new_doc_id, body={'requests': requests}).execute()

            # 3. Если есть данные для таблицы, заполняем ПЕРВУЮ найденную таблицу
            if table_data and len(table_data) > 0:
                self._fill_table(docs_service, new_doc_id, table_data)

            return f"https://docs.google.com/document/d/{new_doc_id}/edit"
            
        except Exception as e:
            return f"Google API Error: {str(e)}"

    def _fill_table(self, docs_service, doc_id, data: List[List[str]]):
        """
        Заполняет таблицу данными. Использует стратегию Reverse-Fill (снизу-вверх, справа-налево),
        чтобы вставка текста не сбивала индексы для следующих вставок.
        """
        # --- ШАГ 1: Создаем строки ---
        doc = docs_service.documents().get(documentId=doc_id).execute()
        body_content = doc.get('body').get('content')
        
        table = None
        table_start_index = None
        for element in body_content:
            if 'table' in element:
                table = element.get('table')
                table_start_index = element.get('startIndex')
                break
        
        if not table: return

        # Вставляем строки в ОБРАТНОМ порядке, всегда под шапку (index 1).
        # Это создает нужные строки в правильном порядке.
        create_rows_req = []
        for _ in reversed(data):
            create_rows_req.append({
                'insertTableRow': {
                    'tableCellLocation': {
                        'tableStartLocation': {'index': table_start_index},
                        'rowIndex': 1  # Индекс 1 - это всегда "сразу после шапки"
                    },
                    'insertBelow': False # Вставляем ПЕРЕД индексом 1 (то есть между шапкой и старыми строками)
                    # Но стоп. insertTableRow работает хитро.
                    # Надежнее так: у нас есть Шапка (0). Мы хотим добавить строку 1.
                    # rowIndex: 1, insertBelow: false -> вставит НАД старой строкой 1 (если она была)
                    # Проще: rowIndex: 0, insertBelow: true -> вставит ПОД шапкой.
                }
            })
            
        # Исправление: Используем insertBelow: True относительно шапки (rowIndex: 0)
        # Если мы делаем это в цикле reversed(data), то:
        # 1. Берем последний элемент (Z). Вставляем под шапку. Таблица: [H, Z]
        # 2. Берем предпоследний (Y). Вставляем под шапку. Таблица: [H, Y, Z]
        # Итог: [H, A, B, C...] - правильный порядок!
        create_rows_req = []
        for _ in reversed(data):
            create_rows_req.append({
                'insertTableRow': {
                    'tableCellLocation': {
                        'tableStartLocation': {'index': table_start_index},
                        'rowIndex': 0
                    },
                    'insertBelow': True
                }
            })

        if create_rows_req:
            docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': create_rows_req}).execute()
        
        # --- ШАГ 2: Заполняем ячейки (Стратегия Двойного Реверса) ---
        # Заново получаем документ с новыми строками
        doc = docs_service.documents().get(documentId=doc_id).execute()
        body_content = doc.get('body').get('content')
        
        # Снова ищем таблицу (ее индекс мог не поменяться, но содержимое поменялось)
        table = None
        for element in body_content:
            if 'table' in element and element.get('startIndex') == table_start_index:
                table = element.get('table')
                break
        
        if not table: return
        rows = table.get('tableRows')

        fill_requests = []
        
        # Нам нужно сопоставить данные со строками.
        # rows[0] - Шапка
        # rows[1]...rows[N] - Наши данные
        
        # Проходимся по данным С КОНЦА списка (снизу вверх по таблице)
        # data[len-1] -> rows[len]
        # data[0] -> rows[1]
        
        total_data_rows = len(data)
        
        # range(total_data_rows - 1, -1, -1) идет от N-1 до 0
        for i in range(total_data_rows - 1, -1, -1):
            row_data = data[i]
            table_row_idx = i + 1 # +1 так как row[0] это шапка
            
            if table_row_idx >= len(rows): continue
            
            doc_row = rows[table_row_idx]
            cells = doc_row.get('tableCells')
            
            # Проходимся по ячейкам С КОНЦА (справа налево)
            # Это гарантирует, что вставка текста справа не сдвинет индексы слева (и сверху)
            for c_idx in range(len(row_data) - 1, -1, -1):
                if c_idx >= len(cells): continue
                
                text_to_insert = str(row_data[c_idx])
                if not text_to_insert: continue
                
                cell = cells[c_idx]
                
                # Ищем куда вставить. Надежнее всего - в конец последнего параграфа ячейки.
                content = cell.get('content', [])
                if not content: continue
                
                # Последний элемент ячейки (обычно параграф, завершающийся \n)
                last_element = content[-1]
                
                if 'paragraph' in last_element:
                    # elements внутри параграфа. Обычно там есть textRun с \n.
                    # endIndex параграфа указывает на позицию ПОСЛЕ \n.
                    # Нам нужно вставить ПЕРЕД \n. Значит endIndex - 1.
                    insert_index = last_element.get('endIndex') - 1
                else:
                    # Fallback
                    insert_index = cell.get('endIndex') - 1
                
                fill_requests.append({
                    'insertText': {
                        'location': {'index': insert_index},
                        'text': text_to_insert
                    }
                })

        if fill_requests:
            docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': fill_requests}).execute()

# Инициализация синглтона
google_service = GoogleDocsService()