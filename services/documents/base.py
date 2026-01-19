from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload
from num2words import num2words

from models import Order, OrderProductLink, OrderServiceLink, CustomerType

# Template IDs
TEMPLATES = {
    "contract": "1QNXCdMHiofUdHIi997R0fvq1ht-vcHkNi5fl3mTa4Zg", 
    "offer": "1_p-XN5Myos5dP20LfYXodKbL8rvIRenZNBhiwqaYpNg",    
    "invoice": "13LlTvDxz5LXu4Wtt9pLkWf7JDG_rnt9vGoi49GMP9dY",
    "work_order": "1tom7jwtOSajR8oCIhSniWEOQFxu2RdwYQcHmEkU34Dc", 
    "act": "1Ttdz0UsuNFJB9FExgxIdvEoHSDc_vippFCq3_I7s3Xw",               
    "tn2": "1LMy6ueY-84FL-5iDcsgGCtLdd4PdK5wpt3tslshgB_E",          
    "ttn1": "19pGneO6T2HDQlWsmhj1kF2oWUmq16hI0EmRHueo6g8I"         
}

DOC_NAMES = {
    "contract": "Договор", 
    "offer": "КП", 
    "invoice": "Счет", 
    "act": "Акт",
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
            selectinload(Order.product_links).selectinload(OrderProductLink.product),
            selectinload(Order.service_links).selectinload(OrderServiceLink.service)
        )
        result = await self.session.execute(query)
        self.order = result.scalar_one_or_none()

    @staticmethod
    def _amount_in_words(amount: float) -> str:
        try:
            text = num2words(amount, lang='ru', to='currency', currency='RUB')
            return text.capitalize() 
        except Exception:
            return str(amount)

    def _prepare_base_variables(self) -> Dict[str, str]:
        if not self.order:
            raise ValueError("Order not fetched")
            
        order = self.order
        c = order.customer

        replacements = {
            "{{order_id}}": str(order.id),
            "{{date}}": datetime.now().strftime("%d.%m.%Y"),
            "{{total_amount}}": f"{order.total_amount:.2f}",
            "{{total_amount_in_words}}": self._amount_in_words(order.total_amount), 
            
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
            "{{bic}}": "-"
        }

        # Technical Meta
        if order.technical_meta and isinstance(order.technical_meta, dict):
            for key, value in order.technical_meta.items():
                replacements[f"{{{{meta_{key}}}}}"] = str(value)

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
    async def generate(self, doc_type: str) -> str:
        pass
