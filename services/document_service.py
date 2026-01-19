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
        query = select(OrderDocument).where(
            OrderDocument.order_id == order_id,
            OrderDocument.doc_type == doc_type
        )
        result = await session.execute(query)
        existing_doc = result.scalar_one_or_none()
        
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
        
        # 4. Копируем шаблон в Google Drive
        file_info = google_service.copy_template(template_id, title)
        
        # 5. Получаем данные заказа и формируем замены
        strategy = DocumentFactory.get_strategy(doc_type, session, order_id)
        await strategy.fetch_order()
        replacements = strategy._prepare_base_variables()
        
        # Добавляем номер документа в замены
        replacements["{{doc_number}}"] = doc_number
        replacements["{{number}}"] = doc_number
        
        # 6. Заменяем плейсхолдеры в документе
        google_service.replace_placeholders(file_info['file_id'], replacements)
        
        # 7. Заполняем таблицу (если есть данные)
        table_data = strategy._prepare_table_data() if hasattr(strategy, '_prepare_table_data') else []
        if table_data and len(table_data) > 0:
            # Определяем, нужен ли footer (строка "Всего")
            has_footer = (doc_type not in ["work_order"])
            
            # Используем внутренний метод google_service для заполнения таблицы
            from googleapiclient.discovery import build
            docs_service = build('docs', 'v1', credentials=google_service.creds)
            google_service._fill_table(docs_service, file_info['file_id'], table_data, has_footer)
        
        # 8. Создаем запись в БД
        new_doc = OrderDocument(
            order_id=order_id,
            doc_type=doc_type,
            number=doc_number,
            date=datetime.now(),
            google_file_id=file_info['file_id'],
            google_edit_url=file_info['edit_url']
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