import os
import logging
import re
from typing import Dict, Any, List, Optional
from io import BytesIO

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload, MediaIoBaseUpload
import datetime

from services.google_oauth_credentials import (
    GoogleCredentialsError,
    GoogleDriveListError,
    GoogleOAuthCredentialStore,
    GoogleTokenExchangeError,
    GoogleTokenPersistenceError,
    GoogleTokenUnavailableError,
)
from services.google_oauth_redirect import (
    LOCAL_GOOGLE_OAUTH_REDIRECT_URI,
    resolve_google_oauth_redirect_uri,
)

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/drive', 
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets'
]
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json").strip() or "token.json"
CLIENT_SECRET_FILE = 'client_secret.json'
DESTINATION_FOLDER_ID = '1kLK6Vque3V5iPV1i1HjeH_su-TmyCzQt' 
DEFAULT_OAUTH_REDIRECT_URI = LOCAL_GOOGLE_OAUTH_REDIRECT_URI


def get_default_oauth_redirect_uri() -> str:
    return resolve_google_oauth_redirect_uri()

class GoogleDocsService:
    def __init__(self):
        self.creds = None
        self._auth_error: GoogleCredentialsError | None = None
        self._authenticate()

    @property
    def auth_error(self) -> GoogleCredentialsError | None:
        return self._auth_error

    @staticmethod
    def _credential_store() -> GoogleOAuthCredentialStore:
        return GoogleOAuthCredentialStore(TOKEN_FILE, SCOPES)

    def get_token_status(self) -> Dict[str, Any]:
        """Return current-process usability and separate durable-store health.

        A refresh can remain usable in memory even when saving it fails, so
        ``valid`` alone must never be treated as proof of durable persistence.
        """
        status = {
            "exists": os.path.exists(TOKEN_FILE),
            "valid": False,
            "expired": False,
            "expiry": None,
            "scopes": [],
            "persistence_ok": self._auth_error is None,
            "persistence_error_code": (
                type(self._auth_error).__name__ if self._auth_error is not None else None
            ),
        }
        if self.creds:
            status["valid"] = self.creds.valid
            status["expired"] = self.creds.expired
            status["scopes"] = self.creds.scopes
            if self.creds.expiry:
                status["expiry"] = self.creds.expiry.strftime("%Y-%m-%d %H:%M:%S")
        return status

    def get_auth_url(self, redirect_uri: Optional[str] = None, *, state: str) -> str:
        """Generates the OAuth2 URL for the user to visit."""
        if not os.path.exists(CLIENT_SECRET_FILE):
             raise Exception(f"Client Secret file '{CLIENT_SECRET_FILE}' not found!")
        if not state:
            raise ValueError("OAuth state is required")
        redirect_uri = redirect_uri or get_default_oauth_redirect_uri()
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRET_FILE,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=state,
        )
        return auth_url

    def finish_auth(self, code: str, redirect_uri: Optional[str] = None):
        """Exchanges auth code for token and saves it."""
        if not os.path.exists(CLIENT_SECRET_FILE):
             raise Exception(f"Client Secret file '{CLIENT_SECRET_FILE}' not found!")
        redirect_uri = redirect_uri or get_default_oauth_redirect_uri()
             
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRET_FILE,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        try:
            flow.fetch_token(code=code)
        except Exception as exc:
            raise GoogleTokenExchangeError(
                "Google OAuth authorization code exchange failed"
            ) from exc

        self.creds = flow.credentials
        self._write_token_file()
        self._auth_error = None
            
        return True

    def _authenticate(self) -> None:
        state = self._credential_store().load()
        self.creds = state.credentials
        self._auth_error = state.error

        if isinstance(state.error, GoogleTokenPersistenceError):
            logger.error(
                "Google OAuth token refresh succeeded but persistence failed "
                "persistence_state=failed credentials_valid=%s error_type=%s",
                bool(state.credentials and state.credentials.valid),
                type(state.error).__name__,
            )
        elif state.error and not isinstance(state.error, GoogleTokenUnavailableError):
            logger.warning(
                "Google OAuth credentials are unavailable error_type=%s",
                type(state.error).__name__,
            )

    def _require_credentials(self) -> Credentials:
        if self.creds is not None and self.creds.valid:
            if self._auth_error is not None and not isinstance(
                self._auth_error,
                GoogleTokenPersistenceError,
            ):
                raise self._auth_error
            if isinstance(self._auth_error, GoogleTokenPersistenceError):
                try:
                    self._credential_store().persist(self.creds)
                except GoogleTokenPersistenceError as exc:
                    self._auth_error = exc
                    logger.warning(
                        "Google OAuth persistence retry failed error_type=%s",
                        type(exc).__name__,
                    )
                else:
                    self._auth_error = None
                    logger.info("Google OAuth persistence recovered")
            return self.creds

        self._authenticate()
        if self._auth_error is not None and not isinstance(
            self._auth_error,
            GoogleTokenPersistenceError,
        ):
            raise self._auth_error
        if self.creds is not None and self.creds.valid:
            return self.creds
        if self._auth_error is not None:
            raise self._auth_error
        raise GoogleTokenUnavailableError("Google OAuth credentials are unavailable")

    def _write_token_file(self) -> None:
        if self.creds is None:
            raise GoogleTokenUnavailableError("Google OAuth credentials are unavailable")
        try:
            self._credential_store().persist(self.creds)
        except GoogleTokenPersistenceError as exc:
            self._auth_error = exc
            logger.error(
                "Google OAuth credentials were issued but persistence failed "
                "error_type=%s",
                type(exc).__name__,
            )
            raise

    def generate_sheet(self, template_id: str, title: str, replacements: Dict[str, str], 
                       table_data: Optional[List[List[str]]] = None,
                       start_cell_addr: str = None,
                       target_sheet_name: str = None,
                       merge_cols: List[tuple] = None, 
                       draw_borders: bool = False,
                       sheet_format_ranges: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Генерация документа на основе Google Sheets.
        start_cell_addr: Адрес ячейки (напр. "A12").
        target_sheet_name: Имя листа (вкладки), куда писать данные (напр. "ТН-2").
        """
        credentials = self._require_credentials()

        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            sheets_service = build('sheets', 'v4', credentials=credentials)

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
                                       merge_cols, draw_borders, sheet_format_ranges)

            return f"https://docs.google.com/spreadsheets/d/{new_sheet_id}/edit"
            
        except Exception as e:
            return f"Google Sheets API Error: {str(e)}"

    def read_sheet_values(
        self,
        spreadsheet_id: str,
        *,
        sheet_name: Optional[str] = None,
        range_a1: Optional[str] = None,
    ) -> List[List[str]]:
        credentials = self._require_credentials()
        sheets_service = build("sheets", "v4", credentials=credentials)
        query_range = range_a1
        if not query_range:
            query_range = f"{sheet_name}" if sheet_name else "A:Z"
        elif sheet_name and "!" not in query_range:
            query_range = f"{sheet_name}!{query_range}"

        resp = (
            sheets_service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=query_range)
            .execute()
        )
        return resp.get("values", [])

    def extract_spreadsheet_id(self, spreadsheet_id_or_url: str) -> str:
        raw = (spreadsheet_id_or_url or "").strip()
        if not raw:
            return ""
        m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw)
        return m.group(1) if m else raw

    def list_sheet_tabs(self, spreadsheet_id: str) -> List[Dict[str, Any]]:
        credentials = self._require_credentials()
        sheets_service = build("sheets", "v4", credentials=credentials)
        spreadsheet = (
            sheets_service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, includeGridData=False)
            .execute()
        )
        out: List[Dict[str, Any]] = []
        for s in spreadsheet.get("sheets", []):
            props = s.get("properties", {})
            out.append(
                {
                    "title": props.get("title"),
                    "index": props.get("index"),
                    "sheet_id": props.get("sheetId"),
                }
            )
        return out

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
                          merge_cols: List[tuple] = None, draw_borders: bool = False,
                          sheet_format_ranges: Optional[List[Dict[str, Any]]] = None):
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
                logger.warning(f"Sheet '{target_sheet_name}' not found. Falling back to the first visible sheet.")
        
        if not sheet:
             # Попробуем найти первый не скрытый лист
             for s in spreadsheet['sheets']:
                 if not s['properties'].get('hidden', False):
                     sheet = s
                     break
        
        if not sheet: sheet = spreadsheet['sheets'][0]

        sht_id = sheet['properties']['sheetId']
        sheet_title = sheet['properties']['title']
        
        logger.debug(f"Target Sheet: '{sheet_title}' (ID: {sht_id})")

        start_row = -1
        start_col = -1
        
        if start_cell_addr:
             start_row, start_col = self._parse_a1(start_cell_addr)
        
        if start_row == -1:
             # Fallback поиска {{table_start}}
             # (Опущен для краткости, т.к. мы используем адреса)
             logger.error("Marker not found in sheet.")
             return

        logger.debug(f"Table starts at row {start_row+1}, column {start_col+1} (Index: {start_row}, {start_col})")
        
        quoted_title = f"'{sheet_title}'" if " " in sheet_title or not sheet_title.isalnum() else sheet_title

        # 1. Очищаем маркер
        if start_cell_addr:
             clear_range = f"{quoted_title}!{start_cell_addr}"
        else:
             clear_range = f"{quoted_title}!R{start_row+1}C{start_col+1}"
        
        # 2. Вставка строк (Стратегия: Insert All New -> Write -> Delete Old Placeholder)
        # Это гарантирует, что первая строка не сохранит странных артефактов объединения
        rows_to_insert = len(data)
        logger.debug(f"Data rows: {len(data)}. Inserting {rows_to_insert} clean rows at {start_row}")
        
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
        logger.debug(f"Unmerging cells from Row {start_row} to {start_row + len(data)}")
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

        # 2.3.1. Выравнивание данных в таблицах Google Sheets.
        # Диапазоны задаются абсолютными 0-based колонками Google Sheets.
        for fmt in sheet_format_ranges or []:
            cols = fmt.get('cols')
            alignment = fmt.get('alignment')
            if not cols or len(cols) != 2 or alignment not in {'LEFT', 'CENTER', 'RIGHT'}:
                continue

            row_mode = fmt.get('rows', 'all')
            row_start = start_row
            row_end = start_row + len(data)
            if row_mode == 'body':
                row_end = max(row_start, row_end - 1)
            elif row_mode == 'footer':
                row_start = max(row_start, row_end - 1)

            if row_end <= row_start:
                continue

            user_format = {
                'horizontalAlignment': alignment,
                'verticalAlignment': 'MIDDLE',
            }
            fields = [
                'userEnteredFormat.horizontalAlignment',
                'userEnteredFormat.verticalAlignment',
            ]
            wrap_strategy = fmt.get('wrap_strategy')
            if wrap_strategy in {'WRAP', 'OVERFLOW_CELL', 'CLIP'}:
                user_format['wrapStrategy'] = wrap_strategy
                fields.append('userEnteredFormat.wrapStrategy')

            reqs.append({
                'repeatCell': {
                    'range': {
                        'sheetId': sht_id,
                        'startRowIndex': row_start,
                        'endRowIndex': row_end,
                        'startColumnIndex': cols[0],
                        'endColumnIndex': cols[1],
                    },
                    'cell': {
                        'userEnteredFormat': user_format
                    },
                    'fields': ','.join(fields),
                }
            })
        
        # 2.4 Удаление старой строки-шаблона (которая оказалась ниже вставленных)
        # Она теперь индексируется как start_row + rows_to_insert
        logger.debug(f"Deleting old placeholder row at {start_row + rows_to_insert}")
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

        if sheet_format_ranges:
            reqs.append({
                'autoResizeDimensions': {
                    'dimensions': {
                        'sheetId': sht_id,
                        'dimension': 'ROWS',
                        'startIndex': start_row,
                        'endIndex': start_row + len(data),
                    }
                }
            })

        try:
            sheets_service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={'requests': reqs}).execute()
        except Exception as e:
            logger.error(f"Error during Insert/Modify/Delete: {e}")

        # 3. Запись данных
        new_values = []
        for row in data:
            new_values.append([{'userEnteredValue': {'stringValue': str(x)}} for x in row])
        
        logger.debug(f"Writing data starting at Row {start_row}, Col {start_col}")

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
             logger.error(f"Error during Write Data: {e}")

    def generate_doc(self, template_id: str, title: str, replacements: Dict[str, str], 
                     table_data: Optional[List[List[str]]] = None, 
                     has_footer: bool = False) -> str:
        """
        has_footer=True: Включает режим объединения ячеек в последней строке таблицы (Итого).
        """
        credentials = self._require_credentials()

        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            docs_service = build('docs', 'v1', credentials=credentials)

            # 1. Копируем
            copy_body = {'name': title, 'parents': [DESTINATION_FOLDER_ID] if DESTINATION_FOLDER_ID else []}
            new_file = drive_service.files().copy(fileId=template_id, body=copy_body).execute()
            new_doc_id = new_file.get('id')

            # 2. Условные блоки и замены
            self.render_conditional_blocks(docs_service, new_doc_id, replacements)
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
        credentials = self._require_credentials()
        drive_service = build('drive', 'v3', credentials=credentials)
        
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
        credentials = self._require_credentials()
        
        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            
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
        credentials = self._require_credentials()
        
        try:
            docs_service = build('docs', 'v1', credentials=credentials)
            self.render_conditional_blocks(docs_service, file_id, replacements)
            
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

    @staticmethod
    def _is_truthy_template_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return bool(value)

    @staticmethod
    def _replacement_value_for_condition(replacements: Dict[str, Any], name: str) -> Any:
        return replacements.get(f"{{{{{name}}}}}", replacements.get(name))

    @staticmethod
    def _iter_text_runs(elements: List[Dict[str, Any]]):
        for element in elements or []:
            if "paragraph" in element:
                for paragraph_element in element["paragraph"].get("elements", []):
                    text_run = paragraph_element.get("textRun")
                    if text_run and "content" in text_run:
                        yield {
                            "text": text_run.get("content", ""),
                            "start": paragraph_element.get("startIndex"),
                            "end": paragraph_element.get("endIndex"),
                        }
            if "table" in element:
                for row in element["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        yield from GoogleDocsService._iter_text_runs(cell.get("content", []))
            if "tableOfContents" in element:
                yield from GoogleDocsService._iter_text_runs(element["tableOfContents"].get("content", []))

    @staticmethod
    def _expand_to_line_boundaries(text: str, start: int, end: int) -> tuple[int, int]:
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        before_marker = text[line_start:start]
        after_marker = text[end:line_end] if line_end != -1 else text[end:]
        if before_marker.strip() == "" and after_marker.strip() == "":
            return line_start, line_end + 1 if line_end != -1 else end
        return start, end

    @staticmethod
    def _build_conditional_block_requests(document: Dict[str, Any], replacements: Dict[str, Any]) -> List[Dict[str, Any]]:
        runs = [
            run for run in GoogleDocsService._iter_text_runs(document.get("body", {}).get("content", []))
            if run.get("text") and run.get("start") is not None and run.get("end") is not None
        ]
        if not runs:
            return []

        full_text_parts: List[str] = []
        spans: List[tuple[int, int, int]] = []
        cursor = 0
        for run in runs:
            text = run["text"]
            spans.append((cursor, int(run["start"]), len(text)))
            full_text_parts.append(text)
            cursor += len(text)
        full_text = "".join(full_text_parts)

        def doc_index(offset: int) -> int:
            for text_offset, start_index, length in spans:
                if text_offset <= offset <= text_offset + length:
                    return start_index + (offset - text_offset)
            last_offset, last_start, last_length = spans[-1]
            return last_start + last_length + max(0, offset - (last_offset + last_length))

        requests: List[Dict[str, Any]] = []
        marker_re = re.compile(r"{{#if\s+([A-Za-z0-9_]+)\s*}}")
        close_marker = "{{/if}}"
        search_from = 0
        while True:
            opening = marker_re.search(full_text, search_from)
            if not opening:
                break
            close_start = full_text.find(close_marker, opening.end())
            if close_start == -1:
                break
            close_end = close_start + len(close_marker)
            condition_name = opening.group(1)
            condition_value = GoogleDocsService._replacement_value_for_condition(replacements, condition_name)
            if GoogleDocsService._is_truthy_template_value(condition_value):
                ranges = [
                    GoogleDocsService._expand_to_line_boundaries(full_text, opening.start(), opening.end()),
                    GoogleDocsService._expand_to_line_boundaries(full_text, close_start, close_end),
                ]
            else:
                ranges = [GoogleDocsService._expand_to_line_boundaries(full_text, opening.start(), close_end)]

            for start, end in ranges:
                if end > start:
                    requests.append({
                        "deleteContentRange": {
                            "range": {
                                "startIndex": doc_index(start),
                                "endIndex": doc_index(end),
                            }
                        }
                    })
            search_from = close_end

        requests.sort(key=lambda item: item["deleteContentRange"]["range"]["startIndex"], reverse=True)
        return requests

    def render_conditional_blocks(self, docs_service: Any, file_id: str, replacements: Dict[str, Any]) -> None:
        document = docs_service.documents().get(documentId=file_id).execute()
        requests = self._build_conditional_block_requests(document, replacements)
        if requests:
            docs_service.documents().batchUpdate(
                documentId=file_id,
                body={"requests": requests},
            ).execute()
    
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
        credentials = self._require_credentials()
        
        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            
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

        # 2.1. Выравнивание строк с позициями:
        # № и ед. изм. — по центру, название — влево, количество/цена/сумма — вправо.
        doc = docs_service.documents().get(documentId=doc_id).execute()
        table = None
        for element in doc.get('body').get('content'):
            if 'table' in element and element.get('startIndex') == table_start_index:
                table = element.get('table')
                break

        alignment_reqs = (
            self._build_standard_table_alignment_requests(table, len(data), has_footer)
            if table
            else []
        )
        if alignment_reqs:
            docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': alignment_reqs}).execute()

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
            
            style_reqs = self._build_footer_table_style_requests(cells)

            if style_reqs:
                docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': style_reqs}).execute()

    @staticmethod
    def _build_standard_table_alignment_requests(
        table: Dict[str, Any],
        data_rows_count: int,
        has_footer: bool,
    ) -> List[Dict[str, Any]]:
        if not table or data_rows_count <= 0:
            return []

        rows = table.get('tableRows') or []
        body_rows_count = max(data_rows_count - 1, 0) if has_footer else data_rows_count
        column_alignment = {
            0: 'CENTER',
            1: 'START',
            2: 'CENTER',
            3: 'END',
            4: 'END',
            5: 'END',
        }
        requests: List[Dict[str, Any]] = []

        for data_idx in range(body_rows_count):
            table_row_idx = data_idx + 1  # row 0 is the template header
            if table_row_idx >= len(rows):
                continue
            cells = rows[table_row_idx].get('tableCells') or []
            for column_idx, alignment in column_alignment.items():
                if column_idx >= len(cells):
                    continue
                cell = cells[column_idx]
                start = cell.get('startIndex')
                end = cell.get('endIndex')
                if start is None or end is None or end <= start:
                    continue
                requests.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': start, 'endIndex': end},
                        'paragraphStyle': {'alignment': alignment},
                        'fields': 'alignment',
                    }
                })

        return requests

    @staticmethod
    def _build_footer_table_style_requests(cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not cells:
            return []

        requests: List[Dict[str, Any]] = []
        footer_cells = [cells[0]]
        if len(cells) > 1:
            footer_cells.append(cells[-1])

        for cell in footer_cells:
            start = cell.get('startIndex')
            end = cell.get('endIndex')
            if start is None or end is None or end <= start:
                continue
            cell_range = {'startIndex': start, 'endIndex': end}
            requests.append({
                'updateTextStyle': {
                    'range': cell_range,
                    'textStyle': {'bold': True},
                    'fields': 'bold',
                }
            })
            requests.append({
                'updateParagraphStyle': {
                    'range': cell_range,
                    'paragraphStyle': {'alignment': 'END'},
                    'fields': 'alignment',
                }
            })

        return requests


    def delete_file(self, file_id: str) -> None:
        """
        Перемещает файл в корзину Google Drive.
        
        Args:
            file_id: ID файла в Google Drive
        """
        try:
            self.delete_file_strict(file_id)
        except Exception as e:
            # Логируем ошибку, но не прерываем выполнение (файл мог быть уже удален)
            logger.warning(f"Failed to delete Google Drive file {file_id}: {str(e)}")

    def delete_file_strict(self, file_id: str) -> None:
        """Move a file to trash and surface retryable provider failures.

        A missing file is already in the desired state and is therefore
        treated as success. Durable cleanup workers use this strict variant;
        legacy best-effort callers keep using ``delete_file``.
        """
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            raise ValueError("Google Drive file_id is required")
        credentials = self._require_credentials()
        drive_service = build("drive", "v3", credentials=credentials)
        try:
            drive_service.files().update(
                fileId=normalized_file_id,
                body={"trashed": True},
            ).execute()
        except HttpError as exc:
            if getattr(exc.resp, "status", None) == 404:
                return
            raise


    def upload_file(self, file_path: str, filename: str, mime_type: str, folder_id: str = None) -> str:
        """
        Загружает файл на Google Drive.
        
        Args:
            file_path: Путь к локальному файлу
            filename: Имя файла в Google Drive
            mime_type: MIME тип файла
            folder_id: ID папки (опционально)
            
        Returns:
            ID загруженного файла
        """
        credentials = self._require_credentials()
        
        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            
            file_metadata = {'name': filename}
            if folder_id:
                file_metadata['parents'] = [folder_id]
                
            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
            
            file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            
            return file.get('id')
        except Exception as e:
            raise Exception(f"Google Drive Upload Error: {str(e)}")

    def create_document_from_html(self, title: str, html: str, folder_id: str = None) -> Dict[str, str]:
        """Creates an editable Google Doc by uploading HTML and converting it."""
        credentials = self._require_credentials()

        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            file_metadata = {
                'name': title,
                'mimeType': 'application/vnd.google-apps.document',
            }
            target_folder_id = folder_id or DESTINATION_FOLDER_ID
            if target_folder_id:
                file_metadata['parents'] = [target_folder_id]

            media = MediaIoBaseUpload(
                BytesIO(html.encode('utf-8')),
                mimetype='text/html',
                resumable=False,
            )
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink',
            ).execute()
            file_id = file.get('id')
            return {
                'file_id': file_id,
                'edit_url': file.get('webViewLink') or f"https://docs.google.com/document/d/{file_id}/edit",
            }
        except Exception as e:
            raise Exception(f"Google Drive HTML Upload Error: {str(e)}")

    def download_file(self, file_id: str) -> BytesIO:
        """
        Скачивает файл из Google Drive.

        Args:
            file_id: ID файла в Google Drive

        Returns:
            BytesIO объект с содержимым файла
        """
        credentials = self._require_credentials()

        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            request = drive_service.files().get_media(fileId=file_id)
            file_io = BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            file_io.seek(0)
            return file_io
        except Exception as e:
            raise Exception(f"Google Drive Download Error: {str(e)}")

    def list_files(self, folder_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Возвращает список файлов в папке, отсортированный по дате создания (DESC).
        """
        credentials = self._require_credentials()

        try:
            drive_service = build('drive', 'v3', credentials=credentials)
            
            query = f"'{folder_id}' in parents and trashed = false"
            
            results = drive_service.files().list(
                q=query,
                pageSize=limit,
                fields="nextPageToken, files(id, name, createdTime, mimeType, size)",
                orderBy="createdTime desc"
            ).execute()
            
            return results.get('files', [])
            
        except Exception as exc:
            logger.error(
                "Google Drive list files failed error_type=%s",
                type(exc).__name__,
            )
            raise GoogleDriveListError("Google Drive failed to list files") from exc

_google_service_instance = None

def get_google_service() -> GoogleDocsService:
    global _google_service_instance
    if _google_service_instance is None:
        _google_service_instance = GoogleDocsService()
    return _google_service_instance
