from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import OrderDocument, Order
from services.google_service import google_service
from services.documents.base import TEMPLATES, DOC_NAMES, BaseDocumentStrategy
from services.documents.factory import DocumentFactory


class DocumentService:
    """Сервис для работы с документами заказов через Google Drive"""
    
    @staticmethod
    async def create_or_get_document(
        session: AsyncSession,
        order_id: int,
        doc_type: str = "contract"
    ) -> OrderDocument:
        """
        Создает документ или возвращает существующий.
        
        Args:
            session: Асинхронная сессия БД
            order_id: ID заказа
            doc_type: Тип документа (contract, invoice, offer, act, etc.)
            
        Returns:
            OrderDocument объект с данными о документе
        """
        # 1. Проверяем, есть ли уже такой документ
        # Если есть дубликаты, берем самый новый
        query = select(OrderDocument).where(
            OrderDocument.order_id == order_id,
            OrderDocument.doc_type == doc_type
        ).order_by(OrderDocument.created_at.desc())
        result = await session.execute(query)
        existing_doc = result.scalars().first()
        
        if existing_doc:
            return existing_doc
        
        # 2. Создаем новый документ
        return await DocumentService._create_new_document(session, order_id, doc_type)
    
    @staticmethod
    async def _create_new_document(
        session: AsyncSession,
        order_id: int,
        doc_type: str
    ) -> OrderDocument:
        """Создает новый документ в Google Drive и сохраняет в БД"""
        
        # 1. Получаем template_id
        template_id = TEMPLATES.get(doc_type)
        if not template_id:
            raise ValueError(f"Unknown document type: {doc_type}")
        
        # 2. Генерируем номер документа
        doc_number = await DocumentService._get_next_number(session, doc_type)
        
        # 3. Формируем название документа
        doc_name = DOC_NAMES.get(doc_type, doc_type.upper())
        title = f"{doc_name} {doc_number}"
        
        # 4. Получаем стратегию для подготовки данных
        strategy = DocumentFactory.get_strategy(doc_type, session, order_id)
        await strategy.fetch_order()
        replacements = strategy._prepare_base_variables()
        
        # Добавляем номер документа в замены
        replacements["{{doc_number}}"] = doc_number
        replacements["{{number}}"] = doc_number
        
        # Добавляем специфичные для типа документа замены
        if hasattr(strategy, '_add_specific_replacements'):
            strategy._add_specific_replacements(replacements)
        
        # 5. Определяем тип документа (Docs или Sheets)
        is_sheet = doc_type in ["tn2", "ttn1"]
        
        if is_sheet:
            # Google Sheets документ
            from services.documents.logistics import LogisticsSheetStrategy
            if isinstance(strategy, LogisticsSheetStrategy):
                # Используем старый метод generate для Sheets
                edit_url = await strategy.generate(doc_type)
                
                # Извлекаем file_id из URL
                # URL формат: https://docs.google.com/spreadsheets/d/{file_id}/edit
                import re
                match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', edit_url)
                if match:
                    file_id = match.group(1)
                else:
                    raise ValueError(f"Could not extract file_id from URL: {edit_url}")
            else:
                raise ValueError(f"Expected LogisticsSheetStrategy for {doc_type}")
        else:
            # Google Docs документ
            # 4. Копируем шаблон в Google Drive
            file_info = google_service.copy_template(template_id, title)
            file_id = file_info['file_id']
            edit_url = file_info['edit_url']
            
            # 6. Заменяем плейсхолдеры в документе
            google_service.replace_placeholders(file_id, replacements)
            
            # 7. Заполняем таблицу (если есть данные)
            table_data = strategy._prepare_table_data() if hasattr(strategy, '_prepare_table_data') else []
            if table_data and len(table_data) > 0:
                # Определяем, нужен ли footer (строка "Всего")
                has_footer = (doc_type not in ["work_order"])
                
                # Используем внутренний метод google_service для заполнения таблицы
                from googleapiclient.discovery import build
                docs_service = build('docs', 'v1', credentials=google_service.creds)
                google_service._fill_table(docs_service, file_id, table_data, has_footer)
        
        # 8. Создаем запись в БД
        new_doc = OrderDocument(
            order_id=order_id,
            doc_type=doc_type,
            number=doc_number,
            date=datetime.now(),
            google_file_id=file_id,
            google_edit_url=edit_url
        )
        
        session.add(new_doc)
        await session.commit()
        await session.refresh(new_doc)
        
        return new_doc
    
    @staticmethod
    async def _get_next_number(session: AsyncSession, doc_type: str) -> str:
        """
        Генерирует следующий номер документа.
        Формат: Д-2024-001 (для договоров), КП-2024-001 (для КП), и т.д.
        """
        current_year = datetime.now().year
        
        # Получаем последний документ этого типа за текущий год
        query = select(OrderDocument).where(
            OrderDocument.doc_type == doc_type
        ).order_by(OrderDocument.id.desc())
        
        result = await session.execute(query)
        last_doc = result.scalar_one_or_none()
        
        # Определяем префикс
        prefix_map = {
            "contract": "Д",
            "offer": "КП",
            "invoice": "С",
            "act": "А",
            "work_order": "НЗ",
            "tn2": "ТН2",
            "ttn1": "ТТН1"
        }
        prefix = prefix_map.get(doc_type, doc_type.upper()[:2])
        
        # Вычисляем следующий номер
        if last_doc and str(current_year) in last_doc.number:
            # Извлекаем номер из формата "Д-2024-001"
            try:
                parts = last_doc.number.split('-')
                if len(parts) >= 3:
                    last_num = int(parts[-1])
                    next_num = last_num + 1
                else:
                    next_num = 1
            except (ValueError, IndexError):
                next_num = 1
        else:
            next_num = 1
        
        return f"{prefix}-{current_year}-{next_num:03d}"
    
    @staticmethod
    def _amount_in_words(amount: float) -> str:
        """
        Deprecated: Logic moved to BaseDocumentStrategy.
        Kept for potential legacy calls.
        """
        from services.documents.base import BaseDocumentStrategy
        return BaseDocumentStrategy(None, 0)._amount_in_words(amount)