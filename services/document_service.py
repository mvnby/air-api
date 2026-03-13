from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import OrderDocument, Order
from services.google_service import get_google_service
from services.documents.base import TEMPLATES, DOC_NAMES, BaseDocumentStrategy
from services.documents.factory import DocumentFactory


class DocumentService:
    """Сервис для работы с документами заказов через Google Drive"""

    ALLOWED_DOC_TYPES = {"contract", "invoice", "work_order", "act", "offer", "tn2", "ttn1"}
    
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
    async def generate_manager_order_document(
        session: AsyncSession,
        order_id: int,
        doc_type: str,
    ) -> dict:
        if doc_type not in DocumentService.ALLOWED_DOC_TYPES:
            raise ValueError(f"Unsupported document type: {doc_type}")

        doc = await DocumentService.create_or_get_document(
            session=session,
            order_id=order_id,
            doc_type=doc_type,
        )
        return {
            "doc_id": doc.id,
            "doc_type": doc.doc_type,
            "edit_url": doc.google_edit_url,
        }

    @staticmethod
    async def get_download_stream(
        session: AsyncSession,
        doc_id: int
    ) -> tuple:
        """
        Возвращает поток данных PDF и имя файла.
        """
        query = select(OrderDocument).where(OrderDocument.id == doc_id)
        result = await session.execute(query)
        document = result.scalar_one_or_none()

        if not document:
            return None, None

        try:
            pdf_content = get_google_service().export_file(document.google_file_id, mime_type='application/pdf')
            
            from urllib.parse import quote
            filename = f"{document.number}.pdf"
            filename_encoded = quote(filename)
            
            return pdf_content, filename_encoded
        except Exception as exc:
            raise ValueError(f"Error exporting PDF: {str(exc)}")

    @staticmethod
    async def delete_document(
        session: AsyncSession,
        doc_id: int
    ) -> Optional[int]:
        """
        Удаляет документ из БД и Google Drive.
        Возвращает order_id удаленного документа.
        """
        query = select(OrderDocument).where(OrderDocument.id == doc_id)
        result = await session.execute(query)
        document = result.scalar_one_or_none()

        if not document:
            return None

        order_id = document.order_id

        if document.google_file_id:
            try:
                get_google_service().delete_file(document.google_file_id)
            except Exception as exc:
                print(f"Error deleting file from Drive: {exc}")

        await session.delete(document)
        await session.commit()
        
        return order_id

    @staticmethod
    async def upload_document(
        session: AsyncSession,
        order_id: int,
        file: "fastapi.UploadFile"
    ) -> OrderDocument:
        """
        Загружает произвольный PDF в Google Drive и связывает его с заказом.
        """
        import os
        import tempfile
        import fastapi
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            from services.google_service import get_google_service, DESTINATION_FOLDER_ID
            
            doc_type = "uploaded_pdf"
            file_id = get_google_service().upload_file(
                file_path=tmp_path,
                filename=file.filename,
                mime_type=file.content_type or "application/pdf",
                folder_id=DESTINATION_FOLDER_ID
            )
            
            edit_url = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
            
            current_year = datetime.now().year
            query = select(OrderDocument).where(OrderDocument.order_id == order_id)
            result = await session.execute(query)
            count = len(result.scalars().all())
            doc_number = f"UPL-{current_year}-{count+1}"

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
            
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @staticmethod
    async def list_order_documents(
        session: AsyncSession,
        order_id: int
    ) -> list[OrderDocument]:
        """Возвращает список документов заказа"""
        query = select(OrderDocument).where(
            OrderDocument.order_id == order_id
        ).order_by(OrderDocument.created_at.desc())
        
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_customer_documents(
        session: AsyncSession,
        customer_id: int
    ) -> list[OrderDocument]:
        """Возвращает список всех документов клиента."""
        query = select(OrderDocument).join(Order).where(
            Order.customer_id == customer_id
        ).order_by(OrderDocument.date.desc())
        
        result = await session.execute(query)
        return result.scalars().all()

    
    @staticmethod
    async def _create_new_document(
        session: AsyncSession,
        order_id: int,
        doc_type: str
    ) -> OrderDocument:
        """Создает новый документ в Google Drive и сохраняет в БД"""
        
        if doc_type in ["act", "tn2", "ttn1"]:
            contract_query = select(OrderDocument).where(
                OrderDocument.order_id == order_id,
                OrderDocument.doc_type == "contract"
            )
            result = await session.execute(contract_query)
            if not result.scalars().first():
                raise ValueError("Невозможно создать акт/накладную: отсутствует договор")

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
        replacements = await strategy._prepare_base_variables(doc_number=doc_number, doc_type=doc_type)
        
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
            file_info = get_google_service().copy_template(template_id, title)
            file_id = file_info['file_id']
            edit_url = file_info['edit_url']
            
            # 6. Заменяем плейсхолдеры в документе
            get_google_service().replace_placeholders(file_id, replacements)
            
            # 7. Заполняем таблицу (если есть данные)
            table_data = strategy._prepare_table_data() if hasattr(strategy, '_prepare_table_data') else []
            if table_data and len(table_data) > 0:
                # Определяем, нужен ли footer (строка "Всего")
                has_footer = (doc_type not in ["work_order"])
                
                # Используем внутренний метод get_google_service() для заполнения таблицы
                from googleapiclient.discovery import build
                docs_service = build('docs', 'v1', credentials=get_google_service().creds)
                get_google_service()._fill_table(docs_service, file_id, table_data, has_footer)
        
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
        
        if doc_type in ["invoice", "offer"]:
            order = await session.get(Order, order_id)
            if order and order.status in ["new_lead", "measurement"]:
                from models.common import OrderStatus
                order.status = OrderStatus.PROPOSAL
                session.add(order)

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
        last_doc = result.scalars().first()
        
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
