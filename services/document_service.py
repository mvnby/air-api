from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload
from num2words import num2words 

from models import Order, OrderProductLink, OrderServiceLink, CustomerType
from services.google_service import google_service

# ID ваших шаблонов
TEMPLATES = {
    "contract": "1QNXCdMHiofUdHIi997R0fvq1ht-vcHkNi5fl3mTa4Zg", 
    "offer": "1_p-XN5Myos5dP20LfYXodKbL8rvIRenZNBhiwqaYpNg",    
    "invoice": "13LlTvDxz5LXu4Wtt9pLkWf7JDG_rnt9vGoi49GMP9dY",
    "work_order": "1tom7jwtOSajR8oCIhSniWEOQFxu2RdwYQcHmEkU34Dc", # Наряд-заказ (для монтажников)
    "act": "1Ttdz0UsuNFJB9FExgxIdvEoHSDc_vippFCq3_I7s3Xw"               # Акт выполненных работ
}

class DocumentService:
    @staticmethod
    def _amount_in_words(amount: float) -> str:
        """
        Конвертирует число в сумму прописью (рубли/копейки).
        Пример: "Пятнадцать тысяч двести четыре рубля 00 копеек"
        """
        try:
            # num2words генерирует строку вида "сто рублей ноль копеек"
            text = num2words(amount, lang='ru', to='currency', currency='RUB')
            return text.capitalize() 
        except Exception:
            return str(amount)

    @staticmethod
    async def create_document(session: AsyncSession, order_id: int, doc_type: str = "contract") -> str:
        template_id = TEMPLATES.get(doc_type)
        if not template_id:
            return f"Ошибка: Неизвестный тип документа {doc_type}"

        # 1. Загрузка данных
        query = select(Order).where(Order.id == order_id).options(
            selectinload(Order.customer),
            selectinload(Order.product_links).selectinload(OrderProductLink.product),
            selectinload(Order.service_links).selectinload(OrderServiceLink.service)
        )
        result = await session.execute(query)
        order = result.scalar_one_or_none()

        if not order: return "Error: Order not found"
        
        c = order.customer
        
        # 2. Подготовка данных (Значения по умолчанию)
        replacements = {
            "{{order_id}}": str(order.id),
            "{{date}}": datetime.now().strftime("%d.%m.%Y"),
            "{{total_amount}}": f"{order.total_amount:.2f}",
            "{{total_amount_in_words}}": DocumentService._amount_in_words(order.total_amount), 
            
            # Дефолтные значения (если клиента нет или поля пустые)
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

        # Добавляем технические мета-данные (для Наряд-заказа)
        if order.technical_meta and isinstance(order.technical_meta, dict):
            for key, value in order.technical_meta.items():
                replacements[f"{{{{meta_{key}}}}}"] = str(value)

        # Если клиент есть в базе, подставляем его реальные поля
        if c:
            # Логика имени: Юрлицо -> Полное название, Физлицо -> Просто имя
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
                
                # Твои существующие поля
                "{{signer_position}}": c.signer_position or "директора",
                "{{signer_name}}": c.signer_name or "_______________________________________",
                "{{acting_basis}}": c.acting_basis or "Устава",
                "{{bank_name}}": c.bank_name or "-",
                "{{iban}}": c.iban or "-",
                "{{bic}}": c.bic or "-"
            })

        # 3. Формирование контента в зависимости от типа документа
        
        # --- WORK ORDER (Наряд-заказ) ---
        # Монтажникам не нужна таблица с ценами, им нужен список оборудования и мета-данные.
        if doc_type == "work_order":
            equipment_lines = []
            counter = 1
            # Только товары (оборудование)
            for link in order.product_links:
                title = link.product.title if link.product else "Оборудование"
                equipment_lines.append(f"{counter}. {title} — {link.quantity} шт.")
                counter += 1
            
            # Добавим услуги, если важно (обычно монтажникам важно знать что делать)
            # Но пользователь сказал "перечень оборудования". 
            # Добавим услуги как "Работы" для полноты картины? 
            # Пользователь сказал "кондиционер такой-то, трубы столько-то". Трубы - это товар.
            # Оставим только товары (оборудование и материалы)
            
            equipment_list_str = "\n".join(equipment_lines)
            replacements["{{equipment_list}}"] = equipment_list_str
            
            # Таблица не нужна
            table_rows = []

        # --- ACT (Акт выполненных работ) ---
        # Только услуги
        elif doc_type == "act":
            table_rows = []
            counter = 1
            for link in order.service_links:
                title = link.service.title if link.service else "Услуга"
                # 6 колонок (как в шаблоне)
                row = [
                    str(counter), title, "шт.", 
                    str(link.quantity), f"{link.price:.2f}", f"{link.price * link.quantity:.2f}"
                ]
                table_rows.append(row)
                counter += 1
            
            # Строка итогов
            if table_rows:
                total_services = sum(l.price * l.quantity for l in order.service_links)
                total_row = ["Всего:", "", "", "", "", f"{total_services:.2f}"]
                table_rows.append(total_row)

        # --- CONTRACT / OFFER (Договор / КП) ---
        # Товары + Услуги (как сейчас)
        # --- INVOICE (Счет) ---
        # Обычно тоже все вместе, но если пользователь захочет разделить, можно добавить условие.
        else:
            table_rows = []
            counter = 1
            
            # Товары
            for link in order.product_links:
                title = link.product.title if link.product else "Товар"
                row = [
                    str(counter), title, "шт.", 
                    str(link.quantity), f"{link.price:.2f}", f"{link.price * link.quantity:.2f}"
                ]
                table_rows.append(row)
                counter += 1

            # Услуги
            for link in order.service_links:
                title = link.service.title if link.service else "Услуга"
                row = [
                    str(counter), title, "шт.", 
                    str(link.quantity), f"{link.price:.2f}", f"{link.price * link.quantity:.2f}"
                ]
                table_rows.append(row)
                counter += 1

            if table_rows:
                total_row = ["Всего:", "", "", "", "", f"{order.total_amount:.2f}"]
                table_rows.append(total_row)

        doc_names = {"contract": "Договор", "offer": "КП", "invoice": "Счет"}
        doc_title = f"{doc_names.get(doc_type, 'Док')} #{order.id} {replacements['{{client_name}}']}"
        
        # 4. Генерация (передаем флаг has_footer=True)
        link = google_service.generate_doc(template_id, doc_title, replacements, table_rows, has_footer=True)
        return link