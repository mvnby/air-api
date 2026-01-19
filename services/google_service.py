import os.path
from typing import Dict, Any, List, Optional
from io import BytesIO

from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import datetime

SCOPES = [
    'https://www.googleapis.com/auth/drive', 
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets'
]
TOKEN_FILE = 'token.json'
CLIENT_SECRET_FILE = 'client_secret.json'
DESTINATION_FOLDER_ID = '1kLK6Vque3V5iPV1i1HjeH_su-TmyCzQt' 

class GoogleDocsService:
    def __init__(self):
        self.creds = None
        self._authenticate()

    def get_token_status(self) -> Dict[str, Any]:
        """Returns status of current token."""
        status = {
            "exists": os.path.exists(TOKEN_FILE),
            "valid": False,
            "expired": False,
            "expiry": None,
            "scopes": []
        }
        if self.creds:
            status["valid"] = self.creds.valid
            status["expired"] = self.creds.expired
            status["scopes"] = self.creds.scopes
            if self.creds.expiry:
                status["expiry"] = self.creds.expiry.strftime("%Y-%m-%d %H:%M:%S")
        return status

    def get_auth_url(self) -> str:
        """Generates the OAuth2 URL for the user to visit."""
        if not os.path.exists(CLIENT_SECRET_FILE):
             raise Exception(f"Client Secret file '{CLIENT_SECRET_FILE}' not found!")
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRET_FILE,
            scopes=SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )
        auth_url, _ = flow.authorization_url(prompt='consent')
        return auth_url

    def finish_auth(self, code: str):
        """Exchanges auth code for token and saves it."""
        if not os.path.exists(CLIENT_SECRET_FILE):
             raise Exception(f"Client Secret file '{CLIENT_SECRET_FILE}' not found!")
             
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRET_FILE,
            scopes=SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )
        flow.fetch_token(code=code)
        self.creds = flow.credentials
        
        # Save
        with open(TOKEN_FILE, 'w') as token:
            token.write(self.creds.to_json())
            
        return True

    def _authenticate(self):
        if os.path.exists(TOKEN_FILE):
            try:
                self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            except Exception: self.creds = None
        
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    # Сохраняем токен ТОЛЬКО если успешно обновили
                    with open(TOKEN_FILE, 'w') as token: token.write(self.creds.to_json())
                except Exception: self.creds = None

    def generate_sheet(self, template_id: str, title: str, replacements: Dict[str, str], 
                       table_data: Optional[List[List[str]]] = None,
                       start_cell_addr: str = None,
                       target_sheet_name: str = None,
                       merge_cols: List[tuple] = None, 
                       draw_borders: bool = False) -> str:
        """
        Генерация документа на основе Google Sheets.
        start_cell_addr: Адрес ячейки (напр. "A12").
        target_sheet_name: Имя листа (вкладки), куда писать данные (напр. "ТН-2").
        """
        if not self.creds or not self.creds.valid:
            self._authenticate()
            if not self.creds: return "Ошибка: Нет доступа к Google API (проверьте права)."

        try:
            drive_service = build('drive', 'v3', credentials=self.creds)
            sheets_service = build('sheets', 'v4', credentials=self.creds)

            # 1. Копируем файл
            copy_body = {'name': title, 'parents': [DESTINATION_FOLDER_ID] if DESTINATION_FOLDER_ID else []}
            new_file = drive_service.files().copy(fileId=template_id, body=copy_body).execute()
            new_sheet_id = new_file.get('id')
            
            # 2. Замены текста (глобально)
            # Примечание: findReplace работает по всем листам, если allSheets=True.
            requests = []
            for key, value in replacements.items():
                requests.append({
                    'findReplace': {
                        'find': key,
                        'replacement': str(value) if value is not None else "",
                        'allSheets': True,
                        'matchCase': True
                    }
                })
            
            if requests:
                sheets_service.spreadsheets().batchUpdate(spreadsheetId=new_sheet_id, body={'requests': requests}).execute()

            # 3. Заполнение таблицы
            if table_data and len(table_data) > 0:
                self._fill_sheet_table(sheets_service, new_sheet_id, table_data, 
                                       start_cell_addr, target_sheet_name,
                                       merge_cols, draw_borders)

            return f"https://docs.google.com/spreadsheets/d/{new_sheet_id}/edit"
            
        except Exception as e:
            return f"Google Sheets API Error: {str(e)}"

    def _parse_a1(self, addr: str):
        """Парсит A1 нотацию (напр 'B12') в (row_index, col_index)"""
        # Упрощенный парсер
        import re
        match = re.match(r"([A-Za-z]+)([0-9]+)", addr)
        if not match: return -1, -1
        col_str, row_str = match.groups()
        
        row_idx = int(row_str) - 1
        
        col_idx = 0
        for i, c in enumerate(reversed(col_str.upper())):
            col_idx += (ord(c) - 64) * (26 ** i)
        col_idx -= 1
        
        return row_idx, col_idx

    def _fill_sheet_table(self, sheets_service, sheet_id, data: List[List[str]], 
                          start_cell_addr=None, target_sheet_name=None,
                          merge_cols: List[tuple] = None, draw_borders: bool = False):
        """
        merge_cols: список кортежей (start_col_idx, end_col_idx) для объединения ВНУТРИ каждой строки данных.
                    Индексы 0-based. start включительно, end исключительно.
        draw_borders: если True, рисует границы для всех ячеек таблицы.
        """
        spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=sheet_id, includeGridData=False).execute()
        
        # Находим нужный лист
        sheet = None
        if target_sheet_name:
            for s in spreadsheet['sheets']:
                if s['properties']['title'] == target_sheet_name:
                    sheet = s
                    break
            if not sheet:
                print(f"⚠️ Warning: Sheet '{target_sheet_name}' not found. Falling back to the first visible sheet.")
        
        if not sheet:
             # Попробуем найти первый не скрытый лист
             for s in spreadsheet['sheets']:
                 if not s['properties'].get('hidden', False):
                     sheet = s
                     break
        
        if not sheet: sheet = spreadsheet['sheets'][0]

        sht_id = sheet['properties']['sheetId']
        sheet_title = sheet['properties']['title']
        
        print(f"🎯 Target Sheet: '{sheet_title}' (ID: {sht_id})")

        start_row = -1
        start_col = -1
        
        if start_cell_addr:
             start_row, start_col = self._parse_a1(start_cell_addr)
        
        if start_row == -1:
             # Fallback поиска {{table_start}}
             # (Опущен для краткости, т.к. мы используем адреса)
             print("❌ Ошибка: Маркер не найден.")
             return

        print(f"✅ Таблица начинается в строке {start_row+1}, столбце {start_col+1} (Index: {start_row}, {start_col})")
        
        quoted_title = f"'{sheet_title}'" if " " in sheet_title or not sheet_title.isalnum() else sheet_title

        # 1. Очищаем маркер
        if start_cell_addr:
             clear_range = f"{quoted_title}!{start_cell_addr}"
        else:
             clear_range = f"{quoted_title}!R{start_row+1}C{start_col+1}"
        
        # 2. Вставка строк (Стратегия: Insert All New -> Write -> Delete Old Placeholder)
        # Это гарантирует, что первая строка не сохранит странных артефактов объединения
        rows_to_insert = len(data)
        print(f"📊 Data rows: {len(data)}. Inserting {rows_to_insert} clean rows at {start_row}")
        
        reqs = []
        if rows_to_insert > 0:
            reqs.append({
                'insertDimension': {
                    'range': {
                        'sheetId': sht_id,
                        'dimension': 'ROWS',
                        'startIndex': start_row,
                        'endIndex': start_row + rows_to_insert
                    },
                    'inheritFromBefore': True 
                }
            })
        
        # 2.1. Разъединяем ячейки (начиная со start_row)
        # Так как мы вставили новые строки, они могут быть объединены (если inheritFromBefore скопировал мерж с хедера?)
        # Лучше сделать Unmerge для всего нового блока.
        print(f"🔓 Unmerging cells from Row {start_row} to {start_row + len(data)}")
        reqs.append({
            'unmergeCells': {
                'range': {
                    'sheetId': sht_id,
                    'startRowIndex': start_row,
                    'endRowIndex': start_row + len(data),
                    'startColumnIndex': start_col,
                    'endColumnIndex': start_col + 20 # Запас
                }
            }
        })

        # 2.2. Объединение ячеек (Custom Merge)
        if merge_cols:
            for r_offset in range(len(data)):
                abs_row = start_row + r_offset
                for (m_start_col, m_end_col) in merge_cols:
                    reqs.append({
                        'mergeCells': {
                            'range': {
                                'sheetId': sht_id,
                                'startRowIndex': abs_row,
                                'endRowIndex': abs_row + 1,
                                'startColumnIndex': m_start_col,
                                'endColumnIndex': m_end_col
                            },
                            'mergeType': 'MERGE_ALL'
                        }
                    })

        # 2.3. Границы (Borders)
        if draw_borders:
            max_col_idx = start_col
            if data:
                 max_col_idx = start_col + len(data[0]) 

            reqs.append({
                'updateBorders': {
                    'range': {
                        'sheetId': sht_id,
                        'startRowIndex': start_row,
                        'endRowIndex': start_row + len(data),
                        'startColumnIndex': start_col,
                        'endColumnIndex': max_col_idx
                    },
                    'top': {'style': 'SOLID', 'width': 1, 'color': {'red': 0, 'green': 0, 'blue': 0}},
                    'bottom': {'style': 'SOLID', 'width': 1, 'color': {'red': 0, 'green': 0, 'blue': 0}},
                    'left': {'style': 'SOLID', 'width': 1, 'color': {'red': 0, 'green': 0, 'blue': 0}},
                    'right': {'style': 'SOLID', 'width': 1, 'color': {'red': 0, 'green': 0, 'blue': 0}},
                    'innerHorizontal': {'style': 'SOLID', 'width': 1, 'color': {'red': 0, 'green': 0, 'blue': 0}},
                    'innerVertical': {'style': 'SOLID', 'width': 1, 'color': {'red': 0, 'green': 0, 'blue': 0}},
                }
            })
        
        # 2.4 Удаление старой строки-шаблона (которая оказалась ниже вставленных)
        # Она теперь индексируется как start_row + rows_to_insert
        print(f"🗑️ Deleting old placeholder row at {start_row + rows_to_insert}")
        reqs.append({
            'deleteDimension': {
                'range': {
                    'sheetId': sht_id,
                    'dimension': 'ROWS',
                    'startIndex': start_row + rows_to_insert,
                    'endIndex': start_row + rows_to_insert + 1
                }
            }
        })

        try:
            sheets_service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={'requests': reqs}).execute()
        except Exception as e:
            print(f"❌ Error during Insert/Modify/Delete: {e}")

        # 3. Запись данных
        new_values = []
        for row in data:
            new_values.append([{'userEnteredValue': {'stringValue': str(x)}} for x in row])
        
        print(f"📝 Writing data starting at Row {start_row}, Col {start_col}")

        update_req = [{
            'updateCells': {
                'rows': [{'values': r} for r in new_values],
                'fields': 'userEnteredValue',
                'start': {
                    'sheetId': sht_id,
                    'rowIndex': start_row,
                    'columnIndex': start_col
                }
            }
        }]
        
        try:
            sheets_service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={'requests': update_req}).execute()
        except Exception as e:
             print(f"❌ Error during Write Data: {e}")

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
    
    def copy_template(self, template_id: str, new_title: str) -> Dict[str, str]:
        """
        Копирует Google Doc шаблон и возвращает информацию о файле.
        
        Args:
            template_id: ID шаблона в Google Drive
            new_title: Название нового документа
            
        Returns:
            Dict с ключами:
            - file_id: ID созданного файла
            - edit_url: Ссылка для редактирования
        """
        if not self.creds or not self.creds.valid:
            self._authenticate()
            if not self.creds:
                raise Exception("Ошибка: Нет доступа к Google API.")
        
        try:
            drive_service = build('drive', 'v3', credentials=self.creds)
            
            # Копируем файл
            copy_body = {
                'name': new_title,
                'parents': [DESTINATION_FOLDER_ID] if DESTINATION_FOLDER_ID else []
            }
            new_file = drive_service.files().copy(fileId=template_id, body=copy_body).execute()
            file_id = new_file.get('id')
            
            # Формируем ссылку для редактирования
            edit_url = f"https://docs.google.com/document/d/{file_id}/edit"
            
            return {
                'file_id': file_id,
                'edit_url': edit_url
            }
        except Exception as e:
            raise Exception(f"Google Drive API Error: {str(e)}")
    
    def replace_placeholders(self, file_id: str, replacements: Dict[str, str]) -> None:
        """
        Заменяет плейсхолдеры {{key}} в Google Doc на соответствующие значения.
        
        Args:
            file_id: ID документа в Google Drive
            replacements: Словарь замен {"{{placeholder}}": "value"}
        """
        if not self.creds or not self.creds.valid:
            self._authenticate()
            if not self.creds:
                raise Exception("Ошибка: Нет доступа к Google API.")
        
        try:
            docs_service = build('docs', 'v1', credentials=self.creds)
            
            # Формируем запросы на замену
            requests = []
            for key, value in replacements.items():
                requests.append({
                    'replaceAllText': {
                        'containsText': {'text': key, 'matchCase': True},
                        'replaceText': str(value) if value is not None else ""
                    }
                })
            
            if requests:
                docs_service.documents().batchUpdate(
                    documentId=file_id, 
                    body={'requests': requests}
                ).execute()
        except Exception as e:
            raise Exception(f"Google Docs API Error: {str(e)}")
    
    def export_file(self, file_id: str, mime_type: str = 'application/pdf') -> BytesIO:
        """
        Экспортирует Google Doc в указанный формат.
        
        Args:
            file_id: ID файла в Google Drive
            mime_type: MIME тип для экспорта (по умолчанию PDF)
                      Поддерживаемые: 'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', и др.
        
        Returns:
            BytesIO объект с содержимым файла
        """
        if not self.creds or not self.creds.valid:
            self._authenticate()
            if not self.creds:
                raise Exception("Ошибка: Нет доступа к Google API.")
        
        try:
            drive_service = build('drive', 'v3', credentials=self.creds)
            
            request = drive_service.files().export_media(fileId=file_id, mimeType=mime_type)
            file_io = BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            file_io.seek(0)  # Сбрасываем позицию на начало
            return file_io
        except Exception as e:
            raise Exception(f"Google Drive Export Error: {str(e)}")
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


    def delete_file(self, file_id: str) -> None:
        """
        Перемещает файл в корзину Google Drive.
        
        Args:
            file_id: ID файла в Google Drive
        """
        if not self.creds or not self.creds.valid:
            self._authenticate()
            if not self.creds:
                raise Exception("Ошибка: Нет доступа к Google API.")
                
        try:
            drive_service = build('drive', 'v3', credentials=self.creds)
            
            # Обновляем метаданные файла, устанавливая trashed=True
            drive_service.files().update(fileId=file_id, body={'trashed': True}).execute()
            
        except Exception as e:
            # Логируем ошибку, но не прерываем выполнение (файл мог быть уже удален)
            print(f"Warning: Failed to delete Google Drive file {file_id}: {str(e)}")

google_service = GoogleDocsService()