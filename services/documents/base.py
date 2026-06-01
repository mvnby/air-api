from abc import ABC, abstractmethod
from datetime import datetime
import re
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload
from num2words import num2words

from models import CustomerContract, DocumentTemplate, Order, OrderDocument, OrderProductLink, OrderServiceLink, CustomerType
from services.document_role_service import DocumentRoleService

# Template IDs
TEMPLATES = {
    "contract": "1QNXCdMHiofUdHIi997R0fvq1ht-vcHkNi5fl3mTa4Zg", 
    "offer": "1_p-XN5Myos5dP20LfYXodKbL8rvIRenZNBhiwqaYpNg",    
    "invoice": "13LlTvDxz5LXu4Wtt9pLkWf7JDG_rnt9vGoi49GMP9dY",
    "work_order": "1tom7jwtOSajR8oCIhSniWEOQFxu2RdwYQcHmEkU34Dc", 
    "act": "1Ttdz0UsuNFJB9FExgxIdvEoHSDc_vippFCq3_I7s3Xw",               
    "defect_act": "1-MjndKurd91Ag_s8Fqc0Hhm37YxMITtD59HJ1RN2O_s",
    "tn2": "1LMy6ueY-84FL-5iDcsgGCtLdd4PdK5wpt3tslshgB_E",          
    "ttn1": "19pGneO6T2HDQlWsmhj1kF2oWUmq16hI0EmRHueo6g8I"         
}

DOC_NAMES = {
    "contract": "Договор", 
    "offer": "КП", 
    "invoice": "Счет", 
    "act": "Акт",
    "defect_act": "Дефектный акт",
    "work_order": "Наряд-заказ",
    "tn2": "ТН-2", 
    "ttn1": "ТТН-1"
}

class BaseDocumentStrategy(ABC):
    def __init__(self, session: AsyncSession, order_id: int):
        self.session = session
        self.order_id = order_id
        self.order: Optional[Order] = None

    async def fetch_order(self) -> None:
        query = select(Order).where(Order.id == self.order_id).options(
            selectinload(Order.customer),
            selectinload(Order.customer_branch),
            selectinload(Order.customer_contract),
            selectinload(Order.proposals),
            selectinload(Order.product_links).selectinload(OrderProductLink.product),
            selectinload(Order.service_links).selectinload(OrderServiceLink.service)
        ).execution_options(populate_existing=True)
        result = await self.session.execute(query)
        self.order = result.unique().scalar_one_or_none()


    @staticmethod
    def _amount_in_words(amount: float) -> str:
        try:
            # num2words с to='currency' делит на 100, поэтому используем обычный режим
            rubles = int(amount)
            kopecks = int((amount - rubles) * 100)
            
            # Генерируем текст для рублей
            rubles_text = num2words(rubles, lang='ru')
            
            # Склонение слова "рубль"
            if rubles % 10 == 1 and rubles % 100 != 11:
                rub_word = "рубль"
            elif rubles % 10 in [2, 3, 4] and rubles % 100 not in [12, 13, 14]:
                rub_word = "рубля"
            else:
                rub_word = "рублей"
            
            # Формируем итоговую строку
            if kopecks > 0:
                kopecks_text = num2words(kopecks, lang='ru')
                # Склонение слова "копейка"
                if kopecks % 10 == 1 and kopecks % 100 != 11:
                    kop_word = "копейка"
                elif kopecks % 10 in [2, 3, 4] and kopecks % 100 not in [12, 13, 14]:
                    kop_word = "копейки"
                else:
                    kop_word = "копеек"
                result = f"{rubles_text} {rub_word}, {kopecks_text} {kop_word}"
            else:
                result = f"{rubles_text} {rub_word}, ноль копеек"
            
            return result.capitalize()
        except Exception:
            return str(amount)

    @staticmethod
    def _format_additional_conditions(value: Optional[str]) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        lines = []
        for line in text.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            cleaned = re.sub(r"^(?:[-•]\s*|\d+[\.)]\s*)", "", cleaned).strip()
            if cleaned:
                lines.append(cleaned)
        return "\n".join(lines)

    async def _prepare_base_variables(
        self,
        doc_number: Optional[str] = None,
        doc_type: Optional[str] = None,
        document_date: Optional[datetime] = None,
        base_document: Optional[OrderDocument] = None,
        base_customer_contract: Optional[CustomerContract] = None,
    ) -> Dict[str, str]:
        if not self.order:
            raise ValueError("Order not fetched")
            
        order = self.order
        c = order.customer
        effective_date = document_date or datetime.now()

        replacements = {
            "{{order_id}}": str(order.id),
            "{{date}}": effective_date.strftime("%d.%m.%Y"),
            "{{total_amount}}": f"{order.total_amount:.2f}",
            "{{total_amount_in_words}}": self._amount_in_words(order.total_amount), 
            "{{object_address}}": order.delivery_address or (order.customer_branch.delivery_address if order.customer_branch else "") or "",
            
            # Defaults
            "{{client_name}}": "Клиент",
            "{{phone}}": order.delivery_address or "-",
            "{{email}}": "-",
            "{{inn}}": "-",
            "{{address}}": "-",
            "{{signer_position}}": "директора", 
            "{{signer_name}}": "-",
            "{{acting_basis}}": "Устава",
            "{{bank_name}}": "-",
            "{{iban}}": "-",
            "{{bic}}": "-",
            
            # Contract info - will be populated after fetching contract document
            "{{contract_name}}": "-",
            "{{contract_number}}": "-",
            "{{contract_date}}": order.contract_date.strftime("%d.%m.%Y") if order.contract_date else "-",
            "{{contract_valid_from}}": order.contract_date.strftime("%d.%m.%Y") if order.contract_date else "-",
            "{{contract_valid_until}}": "-",
            "{{invoice_number}}": "-",
            "{{invoice_date}}": "-",
            "{{base_document_type}}": "-",
            "{{base_document_number}}": "-",
            "{{base_document_date}}": "-",
            "{{act_number}}": "1",
            "{{act_sequence_number}}": "1",
            "{{document_role_type}}": DocumentRoleService.effective_role_type(order),
            "{{additional_conditions}}": self._format_additional_conditions(order.additional_conditions),
        }

        # A one-time contract document must always use its own generated number/date,
        # even when the order currently points at a reusable customer contract.
        effective_customer_contract = base_customer_contract or getattr(order, "customer_contract", None)

        if doc_number:
            replacements["{{doc_number}}"] = doc_number
            replacements["{{number}}"] = doc_number
        if doc_type == "invoice" and doc_number:
            replacements["{{invoice_number}}"] = doc_number
            replacements["{{invoice_date}}"] = effective_date.strftime("%d.%m.%Y")
        if doc_type == "offer" and doc_number:
            replacements["{{offer_number}}"] = doc_number
            replacements["{{offer_date}}"] = effective_date.strftime("%d.%m.%Y")

        if doc_type == "contract" and doc_number:
            replacements["{{contract_name}}"] = doc_number
            replacements["{{contract_number}}"] = doc_number
            replacements["{{contract_date}}"] = effective_date.strftime("%d.%m.%Y")
            replacements["{{contract_valid_from}}"] = effective_date.strftime("%d.%m.%Y")
        elif effective_customer_contract:
            contract = effective_customer_contract
            replacements["{{contract_name}}"] = contract.number
            replacements["{{contract_number}}"] = contract.number
            replacements["{{contract_date}}"] = contract.valid_from.strftime("%d.%m.%Y") if contract.valid_from else "-"
            replacements["{{contract_valid_from}}"] = contract.valid_from.strftime("%d.%m.%Y") if contract.valid_from else "-"
            replacements["{{contract_valid_until}}"] = contract.valid_until.strftime("%d.%m.%Y") if contract.valid_until else "-"
        else:
            # Fetch contract document if exists to get contract number
            contract_query = select(OrderDocument).where(
                OrderDocument.order_id == order.id,
                OrderDocument.doc_type == "contract"
            ).order_by(OrderDocument.created_at.desc())
            
            contract_result = await self.session.execute(contract_query)
            contract_doc = contract_result.scalars().first()
            
            if contract_doc:
                replacements["{{contract_name}}"] = contract_doc.number
                replacements["{{contract_number}}"] = contract_doc.number
                # If contract exists and order.contract_date is not set, use contract document date
                if not order.contract_date:
                    replacements["{{contract_date}}"] = contract_doc.date.strftime("%d.%m.%Y")
                    replacements["{{contract_valid_from}}"] = contract_doc.date.strftime("%d.%m.%Y")

        if base_customer_contract:
            replacements["{{base_document_type}}"] = DOC_NAMES.get("contract", "Договор")
            replacements["{{base_document_number}}"] = base_customer_contract.number
            replacements["{{base_document_date}}"] = (
                base_customer_contract.valid_from.strftime("%d.%m.%Y")
                if base_customer_contract.valid_from
                else "-"
            )
            replacements["{{contract_name}}"] = base_customer_contract.number
            replacements["{{contract_number}}"] = base_customer_contract.number
            replacements["{{contract_date}}"] = replacements["{{base_document_date}}"]
            replacements["{{contract_valid_from}}"] = replacements["{{base_document_date}}"]
            replacements["{{contract_valid_until}}"] = (
                base_customer_contract.valid_until.strftime("%d.%m.%Y")
                if base_customer_contract.valid_until
                else "-"
            )

        invoice_doc = None
        if base_document and base_document.doc_type == "invoice":
            invoice_doc = base_document
        else:
            invoice_query = (
                select(OrderDocument)
                .where(OrderDocument.order_id == order.id, OrderDocument.doc_type == "invoice")
                .order_by(OrderDocument.created_at.desc())
            )
            invoice_result = await self.session.execute(invoice_query)
            invoice_doc = invoice_result.scalars().first()

        if invoice_doc:
            replacements["{{invoice_number}}"] = invoice_doc.number
            replacements["{{invoice_date}}"] = invoice_doc.date.strftime("%d.%m.%Y") if invoice_doc.date else "-"

        if base_document:
            replacements["{{base_document_type}}"] = await self._base_document_type_label(base_document)
            replacements["{{base_document_number}}"] = base_document.number
            replacements["{{base_document_date}}"] = base_document.date.strftime("%d.%m.%Y") if base_document.date else "-"
            if base_document.doc_type == "contract":
                replacements["{{contract_name}}"] = base_document.number
                replacements["{{contract_number}}"] = base_document.number
                replacements["{{contract_date}}"] = base_document.date.strftime("%d.%m.%Y") if base_document.date else "-"
                replacements["{{contract_valid_from}}"] = replacements["{{contract_date}}"]
            elif base_document.doc_type == "invoice":
                replacements["{{invoice_number}}"] = base_document.number
                replacements["{{invoice_date}}"] = base_document.date.strftime("%d.%m.%Y") if base_document.date else "-"
            elif base_document.doc_type == "offer":
                replacements["{{offer_number}}"] = base_document.number
                replacements["{{offer_date}}"] = base_document.date.strftime("%d.%m.%Y") if base_document.date else "-"

        # Technical Meta
        if order.technical_meta and isinstance(order.technical_meta, dict):
            for key, value in order.technical_meta.items():
                replacements[f"{{{{meta_{key}}}}}"] = str(value)

        return self._append_placeholder_aliases(self._append_customer_variables(replacements, c))

    async def _base_document_type_label(self, base_document: OrderDocument) -> str:
        default_label = DOC_NAMES.get(base_document.doc_type, base_document.doc_type)
        if not base_document.document_template_id:
            return default_label
        template = base_document.__dict__.get("document_template")
        if not template:
            template = await self.session.get(DocumentTemplate, base_document.document_template_id)
        custom_label = str(getattr(template, "base_document_type_label", "") or "").strip()
        return custom_label or default_label

    @staticmethod
    def _append_placeholder_aliases(replacements: Dict[str, str]) -> Dict[str, str]:
        for key, value in list(replacements.items()):
            if not (key.startswith("{{") and key.endswith("}}")):
                continue
            name = key[2:-2]
            if not name or name.upper() == name:
                continue
            replacements[f"{{{{{name.upper()}}}}}"] = value
        return replacements

    def _append_customer_variables(self, replacements: Dict[str, str], c: Any) -> Dict[str, str]:
        # Customer Real Data
        if c:
            if c.type == CustomerType.company and c.full_legal_name:
                client_main_name = c.full_legal_name
            else:
                client_main_name = c.name

            replacements.update({
                "{{client_name}}": client_main_name,
                "{{phone}}": f"Тел: {c.phone or ''}",
                "{{email}}": f"email: {c.email or '-'}",
                "{{inn}}": c.inn or "-",
                "{{address}}": c.legal_address or c.actual_address or "-",
                "{{signer_position}}": c.signer_position or "директора",
                "{{signer_name}}": c.signer_name or "_______________________________________",
                "{{acting_basis}}": c.acting_basis or "Устава",
                "{{bank_name}}": c.bank_name or "-",
                "{{iban}}": c.iban or "-",
                "{{bic}}": c.bic or "-"
            })
            
        return replacements

    @abstractmethod
    async def generate(self, doc_type: str, **kwargs) -> str:
        pass
