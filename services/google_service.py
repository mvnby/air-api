import os.path
from typing import Dict, Any, List, Optional
from io import BytesIO

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/documents']
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
            except Exception: self.creds = None
        
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    with open(TOKEN_FILE, 'w') as token: token.write(self.creds.to_json())
                except Exception: self.creds = None

    def generate_doc(self, template_id: str, title: str, replacements: Dict[str, str], 
                     table_data: Optional[List[List[str]]] = None, 
                     has_footer: bool = False) -> str:
        """
        has_footer=True: Включает режим объединения ячеек в последней строке таблицы (Итого).
        """
        if not self.creds or not self.creds.valid:
            self._authenticate()
            if not self.creds: return "Ошибка: Нет доступа к Google API."

        try:
            drive_service = build('drive', 'v3', credentials=self.creds)
            docs_service = build('docs', 'v1', credentials=self.creds)

            # 1. Копируем
            copy_body = {'name': title, 'parents': [DESTINATION_FOLDER_ID] if DESTINATION_FOLDER_ID else []}
            new_file = drive_service.files().copy(fileId=template_id, body=copy_body).execute()
            new_doc_id = new_file.get('id')

            # 2. Замены
            requests = []
            for key, value in replacements.items():
                requests.append({
                    'replaceAllText': {
                        'containsText': {'text': key, 'matchCase': True},
                        'replaceText': str(value) if value is not None else ""
                    }
                })
            
            if requests:
                docs_service.documents().batchUpdate(documentId=new_doc_id, body={'requests': requests}).execute()

            # 3. Таблица
            if table_data and len(table_data) > 0:
                self._fill_table(docs_service, new_doc_id, table_data, has_footer)

            return f"https://docs.google.com/document/d/{new_doc_id}/edit"
            
        except Exception as e:
            return f"Google API Error: {str(e)}"
    def export_pdf(self, file_id: str) -> bytes:
        """Скачивает Google Doc как PDF."""
        if not self.creds: self._authenticate()
        drive_service = build('drive', 'v3', credentials=self.creds)
        
        request = drive_service.files().export_media(fileId=file_id, mimeType='application/pdf')
        file_io = BytesIO()
        downloader = MediaIoBaseDownload(file_io, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        return file_io.getvalue()
    def _fill_table(self, docs_service, doc_id, data: List[List[str]], has_footer: bool):
        # ... (Код поиска таблицы и вставки строк - такой же как был) ...
        # (Для краткости использую предыдущую стабильную версию "Double Reverse")
        
        doc = docs_service.documents().get(documentId=doc_id).execute()
        table = None
        table_start_index = None
        for element in doc.get('body').get('content'):
            if 'table' in element:
                table = element.get('table')
                table_start_index = element.get('startIndex')
                break
        if not table: return

        # 1. Вставка строк
        reqs = []
        for _ in reversed(data):
            reqs.append({
                'insertTableRow': {
                    'tableCellLocation': {'tableStartLocation': {'index': table_start_index}, 'rowIndex': 0},
                    'insertBelow': True
                }
            })
        if reqs: docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': reqs}).execute()

        # 2. Заполнение текстом
        doc = docs_service.documents().get(documentId=doc_id).execute()
        table = None
        for element in doc.get('body').get('content'):
            if 'table' in element and element.get('startIndex') == table_start_index:
                table = element.get('table')
                break
        
        rows = table.get('tableRows')
        fill_reqs = []
        total_data_rows = len(data)
        
        for i in range(total_data_rows - 1, -1, -1):
            row_data = data[i]
            table_row_idx = i + 1 
            if table_row_idx >= len(rows): continue
            
            cells = rows[table_row_idx].get('tableCells')
            for c_idx in range(len(row_data) - 1, -1, -1):
                if c_idx >= len(cells): continue
                text = str(row_data[c_idx])
                if not text: continue
                
                content = cells[c_idx].get('content', [])
                if not content: continue
                last_elem = content[-1]
                idx = (last_elem.get('endIndex') - 1) if 'paragraph' in last_elem else (cells[c_idx].get('endIndex') - 1)
                
                fill_reqs.append({'insertText': {'location': {'index': idx}, 'text': text}})
        
        if fill_reqs: docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': fill_reqs}).execute()

        # 3. ФОРМАТИРОВАНИЕ ПОДВАЛА (Footer)
        if has_footer:
            # Нам нужно снова получить индексы, но для mergeTableCells нам нужен rowIndex
            # Последняя строка данных — это rows[len(data)] (так как row 0 это шапка)
            last_row_index = len(data) # Индекс последней строки (она же футер)
            
            footer_reqs = []
            
            # А. Объединение ячеек (столбцы 0-4)
            footer_reqs.append({
                'mergeTableCells': {
                    'tableRange': {
                        'tableCellLocation': {
                            'tableStartLocation': {'index': table_start_index},
                            'rowIndex': last_row_index,
                            'columnIndex': 0
                        },
                        'rowSpan': 1,
                        'columnSpan': 5 # Объединяем 5 колонок
                    }
                }
            })
            
            # Б. Жирный шрифт для всей строки
            # Мы не знаем точные индексы текста после объединения, но мы можем применить стиль к ЯЧЕЙКАМ
            # Или ко всему диапазону таблицы.
            # Проще всего применить стиль к диапазону строк.
            
            # Но merge меняет структуру. Лучше отправить merge отдельным запросом, а стили следующим.
            docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': footer_reqs}).execute()
            
            # В. Стиль (Жирный + Выравнивание)
            # После объединения в последней строке осталось 2 ячейки: [0] (объединенная) и [1] (сумма)
            
            # Получаем структуру заново, чтобы узнать новые индексы текста
            doc = docs_service.documents().get(documentId=doc_id).execute()
            # Находим таблицу
            for element in doc.get('body').get('content'):
                if 'table' in element and element.get('startIndex') == table_start_index:
                    table = element.get('table')
                    break
            
            last_row = table.get('tableRows')[last_row_index]
            cells = last_row.get('tableCells')
            
            style_reqs = []
            
            # Ячейка 1 ("Всего:") - Жирный + По правому краю
            cell_total_label = cells[0]
            start = cell_total_label.get('startIndex')
            end = cell_total_label.get('endIndex')
            
            style_reqs.append({
                'updateTextStyle': {
                    'range': {'startIndex': start, 'endIndex': end},
                    'textStyle': {'bold': True},
                    'fields': 'bold'
                }
            })
            style_reqs.append({
                'updateParagraphStyle': {
                    'range': {'startIndex': start, 'endIndex': end},
                    'paragraphStyle': {'alignment': 'END'}, # По правому краю
                    'fields': 'alignment'
                }
            })
            
            # Ячейка 2 (Сумма) - Жирный
            if len(cells) > 1:
                cell_amount = cells[1]
                start_amt = cell_amount.get('startIndex')
                end_amt = cell_amount.get('endIndex')
                
                style_reqs.append({
                    'updateTextStyle': {
                        'range': {'startIndex': start_amt, 'endIndex': end_amt},
                        'textStyle': {'bold': True},
                        'fields': 'bold'
                    }
                })

            if style_reqs:
                docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': style_reqs}).execute()

google_service = GoogleDocsService()