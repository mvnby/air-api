import json
from datetime import datetime
from typing import Optional, List
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from models import CustomerContract, CustomerType, OrderDocument, Order, GlobalConfig
from services.google_service import get_google_service
from services.documents.base import TEMPLATES, DOC_NAMES, BaseDocumentStrategy
from services.documents.factory import DocumentFactory
from services.document_role_service import DocumentRoleService
from services.document_template_service import DocumentTemplateService


class DocumentService:
    """Сервис для работы с документами заказов через Google Drive"""

    ALLOWED_DOC_TYPES = {"contract", "invoice", "work_order", "act", "defect_act", "offer", "tn2", "ttn1"}
    PROPOSAL_SCOPED_DOC_TYPES = {"offer", "tn2", "ttn1"}
    CLOSING_DOC_TYPES = {"act", "tn2", "ttn1"}
    BASE_DOC_TYPES = {"offer", "contract", "invoice"}
    DOC_NUMBER_PREFIXES = {
        "contract": "Д",
        "offer": "КП",
        "invoice": "С",
        "act": "А",
        "defect_act": "ДА",
        "work_order": "НЗ",
        "tn2": "ТН2",
        "ttn1": "ТТН1",
    }
    ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx"}
    DEFAULT_UPLOAD_MIME_TYPES = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    @staticmethod
    async def get_available_templates(
        session: AsyncSession,
        doc_type: str,
        order_id: Optional[int] = None,
        customer_id: Optional[int] = None,
    ) -> List[dict]:
        """
        Возвращает список доступных шаблонов для данного типа документа.
        Для contract — читает GlobalConfig key 'contract_templates' (JSON).
        Для остальных — возвращает единственный дефолтный шаблон.
        """
        if doc_type in DocumentTemplateService.MANAGED_TYPES:
            try:
                if order_id:
                    return await DocumentTemplateService.get_relevant_templates_for_order(session, order_id, doc_type)
                return await DocumentTemplateService.get_relevant_templates(
                    session,
                    doc_type,
                    customer_id=customer_id,
                )
            except Exception:
                if doc_type != "contract":
                    raise

        default_id = TEMPLATES.get(doc_type)
        default_name = DOC_NAMES.get(doc_type, doc_type)

        if doc_type == "contract":
            try:
                query = select(GlobalConfig).where(GlobalConfig.key == "contract_templates")
                result = await session.execute(query)
                config = result.scalars().first()
                if config and config.value:
                    items = json.loads(config.value)
                    if isinstance(items, list) and len(items) > 0:
                        normalized_items = []
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            normalized_item = DocumentService._normalize_template_item(item)
                            if normalized_item:
                                normalized_items.append(normalized_item)
                        if normalized_items:
                            return normalized_items
            except Exception:
                pass

        # Fallback: единственный шаблон по умолчанию
        if default_id:
            return [{
                "id": default_id,
                "name": f"{default_name} (по умолчанию)",
                "document_role_type": DocumentRoleService.normalize_role_type(None),
                "is_open_contract": False,
            }]
        return []

    @staticmethod
    def _normalize_template_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _normalize_template_item(item: dict) -> dict:
        template_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip() or template_id
        if not template_id:
            return {}
        return {
            "id": template_id,
            "name": name,
            "document_role_type": DocumentRoleService.normalize_role_type(item.get("document_role_type")),
            "is_open_contract": DocumentService._normalize_template_bool(item.get("is_open_contract")),
        }

    @staticmethod
    async def _get_contract_template_role_type(session: AsyncSession, template_id: Optional[str]) -> str:
        if not template_id:
            return DocumentRoleService.normalize_role_type(None)
        templates = await DocumentService.get_available_templates(session, "contract")
        for template in templates:
            if template.get("id") == template_id:
                return DocumentRoleService.normalize_role_type(template.get("document_role_type"))
        return DocumentRoleService.normalize_role_type(None)
    
    @staticmethod
    async def create_or_get_document(
        session: AsyncSession,
        order_id: int,
        doc_type: str = "contract",
        document_template_id: Optional[int] = None,
        template_id: Optional[str] = None,
        contract_date: Optional[datetime] = None,
        proposal_id: Optional[int] = None,
        base_document_id: Optional[int] = None,
    ) -> OrderDocument:
        """
        Создает документ или возвращает существующий.
        
        Args:
            session: Асинхронная сессия БД
            order_id: ID заказа
            doc_type: Тип документа (contract, invoice, offer, act, etc.)
            template_id: Опциональный ID шаблона (Google Drive file ID)
            
        Returns:
            OrderDocument объект с данными о документе
        """
        if doc_type in DocumentService.PROPOSAL_SCOPED_DOC_TYPES or doc_type in DocumentService.CLOSING_DOC_TYPES:
            return await DocumentService._create_new_document(
                session,
                order_id,
                doc_type,
                document_template_id=document_template_id,
                template_id=template_id,
                contract_date=contract_date,
                proposal_id=proposal_id,
                base_document_id=base_document_id,
            )

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
        return await DocumentService._create_new_document(
            session,
            order_id,
            doc_type,
            document_template_id=document_template_id,
            template_id=template_id,
            contract_date=contract_date,
            proposal_id=proposal_id,
            base_document_id=base_document_id,
        )

    @staticmethod
    async def generate_manager_order_document(
        session: AsyncSession,
        order_id: int,
        doc_type: str,
        document_template_id: Optional[int] = None,
        template_id: Optional[str] = None,
        contract_date: Optional[datetime] = None,
        proposal_id: Optional[int] = None,
        base_document_id: Optional[int] = None,
    ) -> dict:
        if doc_type not in DocumentService.ALLOWED_DOC_TYPES:
            raise ValueError(f"Unsupported document type: {doc_type}")

        doc = await DocumentService.create_or_get_document(
            session=session,
            order_id=order_id,
            doc_type=doc_type,
            document_template_id=document_template_id,
            template_id=template_id,
            contract_date=contract_date,
            proposal_id=proposal_id,
            base_document_id=base_document_id,
        )
        return {
            "doc_id": doc.id,
            "proposal_id": getattr(doc, "proposal_id", None),
            "base_document_id": getattr(doc, "base_document_id", None),
            "base_customer_contract_id": getattr(doc, "base_customer_contract_id", None),
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

        if not document.google_file_id:
            raise ValueError("Для этого документа нет загруженного файла")

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
        Загружает произвольный документ в Google Drive и связывает его с заказом.
        """
        import os

        original_filename, suffix = DocumentService._validate_upload_file(file)
        tmp_path = await DocumentService._save_upload_to_temp(file, suffix)

        try:
            from services.google_service import get_google_service, DESTINATION_FOLDER_ID
            
            doc_type = "uploaded_doc"
            file_id = get_google_service().upload_file(
                file_path=tmp_path,
                filename=original_filename,
                mime_type=DocumentService._upload_mime_type(file, suffix),
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
    def _validate_upload_file(file: object) -> tuple[str, str]:
        import os

        original_filename = str(getattr(file, "filename", None) or "").strip()
        if not original_filename:
            raise ValueError("Файл обязателен")

        _, suffix = os.path.splitext(original_filename)
        suffix = suffix.lower()
        if suffix not in DocumentService.ALLOWED_UPLOAD_EXTENSIONS:
            raise ValueError("Поддерживаются только файлы PDF, DOC и DOCX")
        return original_filename, suffix

    @staticmethod
    def _upload_mime_type(file: object, suffix: str) -> str:
        return (
            str(getattr(file, "content_type", None) or "").strip()
            or DocumentService.DEFAULT_UPLOAD_MIME_TYPES.get(suffix)
            or "application/octet-stream"
        )

    @staticmethod
    async def _save_upload_to_temp(file: object, suffix: str) -> str:
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            return tmp.name

    @staticmethod
    async def _upload_document_file(file: object, *, title_prefix: str) -> tuple[str, str]:
        import os

        original_filename, suffix = DocumentService._validate_upload_file(file)
        tmp_path = await DocumentService._save_upload_to_temp(file, suffix)

        try:
            from services.google_service import DESTINATION_FOLDER_ID

            upload_title = f"{title_prefix}{suffix}"
            file_id = get_google_service().upload_file(
                file_path=tmp_path,
                filename=upload_title,
                mime_type=DocumentService._upload_mime_type(file, suffix),
                folder_id=DESTINATION_FOLDER_ID,
            )
            return file_id, f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @staticmethod
    async def attach_file_to_document(
        session: AsyncSession,
        doc_id: int,
        file: "fastapi.UploadFile",
    ) -> Optional[OrderDocument]:
        document = await session.get(OrderDocument, doc_id)
        if not document:
            return None

        previous_file_id = document.google_file_id
        title_prefix = f"{DOC_NAMES.get(document.doc_type, 'Документ')} {document.number}"
        file_id, edit_url = await DocumentService._upload_document_file(file, title_prefix=title_prefix)

        if previous_file_id:
            try:
                get_google_service().delete_file(previous_file_id)
            except Exception as exc:
                print(f"Error deleting replaced file from Drive: {exc}")

        document.google_file_id = file_id
        document.google_edit_url = edit_url
        session.add(document)
        await session.commit()
        await session.refresh(document)
        return document

    @staticmethod
    async def register_external_contract(
        session: AsyncSession,
        *,
        order_id: int,
        number: str,
        contract_date: datetime,
        external_url: Optional[str] = None,
        file: object = None,
    ) -> OrderDocument:
        """Registers a customer-provided one-time contract for closing docs."""
        order = await session.get(Order, order_id)
        if not order:
            raise ValueError("Order not found")

        cleaned_number = str(number or "").strip()
        if not cleaned_number:
            raise ValueError("Номер договора обязателен")

        effective_date = contract_date or datetime.now()
        if effective_date.tzinfo is not None:
            effective_date = effective_date.replace(tzinfo=None)

        cleaned_url = str(external_url or "").strip()
        if cleaned_url:
            from urllib.parse import urlparse

            parsed_url = urlparse(cleaned_url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise ValueError("Ссылка на договор должна начинаться с http:// или https://")
        file_id = ""
        edit_url = cleaned_url

        if file is not None and getattr(file, "filename", None):
            file_id, edit_url = await DocumentService._upload_document_file(
                file,
                title_prefix=f"Договор {cleaned_number}",
            )

        doc = OrderDocument(
            order_id=order_id,
            doc_type="contract",
            number=cleaned_number,
            date=effective_date,
            google_file_id=file_id,
            google_edit_url=edit_url,
        )
        order.customer_contract_id = None
        order.contract_date = effective_date
        session.add(order)
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc

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
    async def _resolve_base_document(
        session: AsyncSession,
        *,
        order_id: int,
        doc_type: str,
        base_document_id: Optional[int],
    ) -> tuple[Optional[OrderDocument], Optional[CustomerContract]]:
        if doc_type not in DocumentService.CLOSING_DOC_TYPES:
            return None, None

        order = await session.get(Order, order_id)
        if not order:
            raise ValueError("Order not found")

        if base_document_id == 0:
            if not order.customer_contract_id:
                raise ValueError("Открытый договор-основание не выбран")
            base_customer_contract = await session.get(CustomerContract, order.customer_contract_id)
            if not base_customer_contract:
                raise ValueError("Открытый договор-основание не найден")
            return None, base_customer_contract

        if base_document_id is not None:
            base_document = await session.get(OrderDocument, base_document_id)
            if not base_document or base_document.order_id != order_id:
                raise ValueError("Документ-основание не найден в этом заказе")
            if base_document.doc_type not in DocumentService.BASE_DOC_TYPES:
                raise ValueError("Документ-основание должен быть договором, счетом или офертой")
            return base_document, None

        query = (
            select(OrderDocument)
            .where(
                OrderDocument.order_id == order_id,
                OrderDocument.doc_type.in_(DocumentService.BASE_DOC_TYPES),
            )
            .order_by(OrderDocument.created_at.desc())
        )
        result = await session.execute(query)
        candidates = list(result.scalars().all())
        base_customer_contract = None
        if order.customer_contract_id:
            base_customer_contract = await session.get(CustomerContract, order.customer_contract_id)

        if len(candidates) + (1 if base_customer_contract else 0) == 0:
            return None, None
        if len(candidates) + (1 if base_customer_contract else 0) > 1:
            raise ValueError("Выберите документ-основание для акта или накладной")
        if candidates:
            return candidates[0], None
        return None, base_customer_contract

    @staticmethod
    async def build_document_basis_lookup(
        session: AsyncSession,
        documents: list[OrderDocument],
    ) -> dict[int, dict]:
        docs_by_id = {doc.id: doc for doc in documents if doc.id is not None}
        contract_ids = {
            doc.base_customer_contract_id
            for doc in documents
            if getattr(doc, "base_customer_contract_id", None) is not None
        }
        contracts_by_id: dict[int, CustomerContract] = {}
        if contract_ids:
            result = await session.execute(select(CustomerContract).where(CustomerContract.id.in_(contract_ids)))
            contracts_by_id = {contract.id: contract for contract in result.scalars().all() if contract.id is not None}

        lookup: dict[int, dict] = {}
        for doc in documents:
            if doc.id is None:
                continue
            base_doc = docs_by_id.get(doc.base_document_id)
            base_contract = contracts_by_id.get(doc.base_customer_contract_id)
            if base_doc:
                lookup[doc.id] = {
                    "base_document_id": base_doc.id,
                    "base_customer_contract_id": None,
                    "base_document_type": base_doc.doc_type,
                    "base_document_number": base_doc.number,
                    "base_document_date": base_doc.date,
                }
            elif base_contract:
                lookup[doc.id] = {
                    "base_document_id": None,
                    "base_customer_contract_id": base_contract.id,
                    "base_document_type": "contract",
                    "base_document_number": base_contract.number,
                    "base_document_date": base_contract.valid_from,
                }
            else:
                lookup[doc.id] = {
                    "base_document_id": None,
                    "base_customer_contract_id": None,
                    "base_document_type": None,
                    "base_document_number": None,
                    "base_document_date": None,
                }
        return lookup

    
    @staticmethod
    async def _create_new_document(
        session: AsyncSession,
        order_id: int,
        doc_type: str,
        document_template_id: Optional[int] = None,
        template_id: Optional[str] = None,
        contract_date: Optional[datetime] = None,
        proposal_id: Optional[int] = None,
        base_document_id: Optional[int] = None,
    ) -> OrderDocument:
        """Создает новый документ в Google Drive и сохраняет в БД"""

        base_document, base_customer_contract = await DocumentService._resolve_base_document(
            session,
            order_id=order_id,
            doc_type=doc_type,
            base_document_id=base_document_id,
        )

        if doc_type in DocumentService.CLOSING_DOC_TYPES:
            order_result = await session.execute(
                select(Order)
                .where(Order.id == order_id)
                .options(selectinload(Order.customer), selectinload(Order.customer_contract))
            )
            order = order_result.scalars().first()
            if not order:
                raise ValueError("Order not found")
            has_stable_base = base_document is not None or base_customer_contract is not None
            if order.customer and order.customer.type == CustomerType.company:
                if not has_stable_base:
                    raise ValueError("Невозможно создать акт/накладную: выберите открытый договор клиента или создайте договор/счет заказа")
            elif not has_stable_base:
                raise ValueError("Невозможно создать акт/накладную: отсутствует договор или счет")

        # 1. Получаем template_id (managed template, legacy query param or default)
        document_template_id, template_id = await DocumentTemplateService.resolve_template_for_generation(
            session,
            order_id=order_id,
            doc_type=doc_type,
            document_template_id=document_template_id,
            template_id=template_id,
            base_document_id=base_document.id if base_document else None,
        )
        if not template_id:
            raise ValueError(f"Unknown document type: {doc_type}")
        
        # 2. Генерируем номер документа
        effective_doc_date = contract_date or datetime.now()
        if effective_doc_date.tzinfo is not None:
            effective_doc_date = effective_doc_date.replace(tzinfo=None)
        doc_number = await DocumentService._get_next_number(session, doc_type, base_date=effective_doc_date)
        
        # 3. Формируем название документа
        doc_name = DOC_NAMES.get(doc_type, doc_type.upper())
        title = f"{doc_name} {doc_number}"
        
        # 4. Получаем стратегию для подготовки данных
        strategy = DocumentFactory.get_strategy(doc_type, session, order_id)
        await strategy.fetch_order()
        effective_proposal_id = (
            DocumentService._apply_proposal_lines(strategy.order, proposal_id)
            if doc_type in DocumentService.PROPOSAL_SCOPED_DOC_TYPES
            else None
        )
        if doc_type == "contract" and strategy.order:
            if not strategy.order.document_role_type:
                strategy.order.document_role_type = await DocumentService._get_contract_template_role_type(session, template_id)
            strategy.order.contract_date = effective_doc_date
            session.add(strategy.order)
        replacements = await strategy._prepare_base_variables(
            doc_number=doc_number,
            doc_type=doc_type,
            document_date=effective_doc_date,
            base_document=base_document,
            base_customer_contract=base_customer_contract,
        )
        if doc_type == "act":
            act_number = await DocumentService._get_act_number_for_order_contract(session, strategy.order)
            replacements["{{act_number}}"] = str(act_number)
            replacements["{{act_sequence_number}}"] = str(act_number)
        
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
                edit_url = await strategy.generate(
                    doc_type,
                    template_id=template_id,
                    doc_number=doc_number,
                    document_date=effective_doc_date,
                    base_document=base_document,
                    base_customer_contract=base_customer_contract,
                )
                
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
            if doc_type in {"act", "invoice"} and strategy.order:
                role_replacements = DocumentRoleService.build_word_replacements(
                    DocumentRoleService.effective_role_type(strategy.order)
                )
                if role_replacements:
                    get_google_service().replace_placeholders(file_id, role_replacements)
            
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
            proposal_id=effective_proposal_id,
            base_document_id=base_document.id if base_document else None,
            base_customer_contract_id=base_customer_contract.id if base_customer_contract else None,
            document_template_id=document_template_id,
            template_id=template_id,
            doc_type=doc_type,
            number=doc_number,
            date=effective_doc_date,
            google_file_id=file_id,
            google_edit_url=edit_url
        )
        
        session.add(new_doc)
        
        if doc_type in ["invoice", "offer"]:
            order = await session.get(Order, order_id)
            if order and order.status in ["new_lead", "measurement"]:
                from models.common import OrderStatus
                order.status = OrderStatus.NEGOTIATION
                order.proposal_status = "sent"
                session.add(order)

        await session.commit()
        await session.refresh(new_doc)
        
        return new_doc

    @staticmethod
    def _apply_proposal_lines(order: Optional[Order], proposal_id: Optional[int]) -> Optional[int]:
        if not order:
            return None

        active_proposals = [proposal for proposal in getattr(order, "proposals", []) if not proposal.is_archived]
        selected = None
        if proposal_id is not None:
            selected = next((proposal for proposal in active_proposals if proposal.id == proposal_id), None)
            if not selected:
                raise ValueError("Proposal not found")
        else:
            selected = (
                next((proposal for proposal in active_proposals if proposal.is_selected), None)
                or next(iter(sorted(active_proposals, key=lambda item: item.sort_order)), None)
            )

        if not selected or selected.id is None:
            return None

        selected_id = int(selected.id)
        product_links = [link for link in order.product_links if link.proposal_id == selected_id]
        service_links = [link for link in order.service_links if link.proposal_id == selected_id]
        total_amount = sum((link.price or 0) * (link.quantity or 0) for link in product_links)
        total_amount += sum((link.price or 0) * (link.quantity or 0) for link in service_links)
        total_cost = sum((link.cost or 0) * (link.quantity or 0) for link in product_links)
        total_cost += sum((link.cost or 0) * (link.quantity or 0) for link in service_links)

        set_committed_value(order, "product_links", product_links)
        set_committed_value(order, "service_links", service_links)
        set_committed_value(order, "total_amount", total_amount)
        set_committed_value(order, "total_cost", total_cost)
        set_committed_value(order, "margin", total_amount - total_cost)
        return selected_id
    
    @staticmethod
    async def _get_next_number(session: AsyncSession, doc_type: str, base_date: Optional[datetime] = None) -> str:
        """
        Генерирует следующий номер документа.
        Формат: Д-2024-001 (для договоров), КП-2024-001 (для КП), и т.д.
        """
        current_year = (base_date or datetime.now()).year

        prefix = DocumentService.DOC_NUMBER_PREFIXES.get(doc_type, doc_type.upper()[:2])
        number_prefix = f"{prefix}-{current_year}-"

        query = (
            select(OrderDocument)
            .where(OrderDocument.number.like(f"{number_prefix}%"))
            .order_by(OrderDocument.id.desc())
        )
        result = await session.execute(query)
        docs = list(result.scalars().all())

        next_num = 1
        for doc in docs:
            try:
                next_num = int(str(doc.number).split("-")[-1]) + 1
                break
            except (ValueError, IndexError):
                continue
        
        return f"{prefix}-{current_year}-{next_num:03d}"

    @staticmethod
    async def _get_act_number_for_order_contract(session: AsyncSession, order: Optional[Order]) -> int:
        if not order or not order.customer_contract_id:
            return 1

        query = (
            select(func.count(OrderDocument.id))
            .join(Order, OrderDocument.order_id == Order.id)
            .where(
                OrderDocument.doc_type == "act",
                Order.customer_contract_id == order.customer_contract_id,
            )
        )
        result = await session.execute(query)
        existing_count = int(result.scalar_one() or 0)
        return existing_count + 1
    
    @staticmethod
    def _amount_in_words(amount: float) -> str:
        """
        Deprecated: Logic moved to BaseDocumentStrategy.
        Kept for potential legacy calls.
        """
        from services.documents.base import BaseDocumentStrategy
        return BaseDocumentStrategy(None, 0)._amount_in_words(amount)
