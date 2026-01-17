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
    "act": "1Ttdz0UsuNFJB9FExgxIdvEoHSDc_vippFCq3_I7s3Xw",               # Акт выполненных работ
    "tn2": "1LMy6ueY-84FL-5iDcsgGCtLdd4PdK5wpt3tslshgB_E",          # ТН-2 (Накладная на отпуск товаров)
    "ttn1": "19pGneO6T2HDQlWsmhj1kF2oWUmq16hI0EmRHueo6g8I"         # ТТН-1 (Товарно-транспортная накладная)
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

        # ТТН-1 Специфичные поля (Авто, Перевозчик)
        if doc_type == "ttn1":
             replacements.update({
                 "{{car_model}}": "-",
                 "{{car_number}}": "-",
                 "{{driver_name}}": "-",
                 "{{carrier}}": "-"
             })

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
        total_services_sum = 0.0 # Default to 0.0 to prevent NameError
        
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
        
        # --- TN-2 / TTN-1 (Накладные) ---
        elif doc_type in ["tn2", "ttn1"]:
            table_rows = []
            
            total_qty = 0
            total_cost_net = 0.0
            total_vat = 0.0
            total_cost_gross = 0.0

            is_ttn1 = (doc_type == "ttn1")
            
            # Map based on User Input
            # Values are Column Letters.
            # We assume the table starts at 'B' (Index 1).
            start_col_letter = 'B'
            
            if is_ttn1:
                # TTN-1 (11 cols)
                # 1.Name, 2.Unit, 3.Qty, 4.Price, 5.Cost, 6.VatRate, 7.VatSum, 8.CostW/VAT, 9.Seats, 10.Mass, 11.Note
                col_map = {
                    0: 'B', 1: 'J', 2: 'K', 3: 'L', 4: 'N', 
                    5: 'R', 6: 'S', 7: 'U', 8: 'W', 9: 'Y', 10: 'AA'
                }
            else:
                # TN-2 (9 cols)
                # 1.Name, 2.Unit, 3.Qty, 4.Price, 5.Cost, 6.VatRate, 7.VatSum, 8.CostW/VAT, 9.Note
                col_map = {
                    0: 'B', 1: 'J', 2: 'K', 3: 'L', 4: 'O', 
                    5: 'S', 6: 'T', 7: 'W', 8: 'AA'
                }

            for link in order.product_links:
                title = link.product.title if link.product else "Товар"
                qty = link.quantity
                price = link.price
                cost = price * qty
                vat_rate = "без НДС" 
                cost_with_vat = cost 

                logical_row = [
                    title,                  # 0
                    "шт.",                  # 1
                    str(qty),               # 2
                    f"{price:.2f}",         # 3
                    f"{cost:.2f}",          # 4
                    vat_rate,               # 5
                    "-",                    # 6
                    f"{cost_with_vat:.2f}", # 7
                ]
                
                if is_ttn1:
                    logical_row.extend([str(qty), "0.00", "X"]) # 8, 9, 10
                else:
                    logical_row.append("X") # 8

                sparse_row = DocumentService._build_sparse_row(logical_row, col_map, start_col_letter)
                table_rows.append(sparse_row)
                
                total_qty += qty
                total_cost_net += cost
                total_cost_gross += cost_with_vat
            
            # ИТОГО
            if table_rows:
                total_logical = [
                    "ИТОГО", "x", str(total_qty), "x", 
                    f"{total_cost_net:.2f}", "x", 
                    "-", f"{total_cost_gross:.2f}"
                ]
                if is_ttn1:
                    total_logical.extend([str(total_qty), "0.00", "X"])
                else:
                    total_logical.append("X")
                
                sparse_total = DocumentService._build_sparse_row(total_logical, col_map, start_col_letter)
                table_rows.append(sparse_total)
                
                # Доп. замены (Total Words / Weight)
                replacements["{{total_qty}}"] = str(total_qty)
                replacements["{{total_vat}}"] = f"{total_vat:.2f}"
                replacements["{{total_with_vat_words}}"] = DocumentService._amount_in_words(total_cost_gross)
                replacements["{{total_qty_words}}"] = num2words(total_qty, lang='ru')
                
                # Вес (попытка достать из specs)
                # Вес (попытка достать из specs)
                total_weight = 0.0
                try:
                    for link in order.product_links:
                         w = 0.0
                         if link.product and link.product.specs:
                             # Ищем ключи weight, weight_net, вес
                             spec_w = link.product.specs.get("weight") or link.product.specs.get("weight_net") or link.product.specs.get("вес")
                             if spec_w:
                                 w = float(spec_w)
                         total_weight += (w * link.quantity)
                except Exception:
                    total_weight = 0.0

                replacements["{{total_weight}}"] = f"{total_weight:.2f}"
                
                # Services Words
                try:
                     services_word_val = num2words(total_services_sum, lang='ru', to='currency', currency='RUB')
                except Exception:
                     services_word_val = f"{total_services_sum:.2f}"
                
                replacements["{{total_services_word}}"] = services_word_val
                replacements["{{sum_word}}"] = services_word_val # Fallback shorter tag

                replacements["{{total_weight_words}}"] = num2words(total_weight, lang='ru')

        # --- CONTRACT / OFFER (Договор / КП) ---
        # Товары + Услуги (как сейчас)
        # --- INVOICE (Счет) ---
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

        doc_names = {"contract": "Договор", "offer": "КП", "invoice": "Счет", "tn2": "ТН-2", "ttn1": "ТТН-1"}
        doc_title = f"{doc_names.get(doc_type, 'Док')} #{order.id} {replacements.get('{{client_name}}', '')}"

        if doc_type in ["tn2", "ttn1"]:
            # TN-2: B19, TTN-1: B22 (User confirmed 22 is first data row)
            if doc_type == "ttn1":
                start_addr = "B22"
                sheet_name = "ТТН-1"
                # TTN-1 Mapping (11 cols)
                # Final Strict Mapping based on User Feedback:
                # gaps between columns are utilized.
                # 0: Name -> B (1) -> Merge B-I (1-9)
                # 1: Unit -> J (9)
                # 2: Qty  -> K (10)
                # 3: Price-> L (11) -> Merge L-M (11-13)
                # 4: Cost -> N (13) -> Merge N-Q (13-17)
                # 5: Rate -> R (17) -> Single (17-18)
                # 6: VAT  -> S (18) -> Merge S-T (18-20)
                # 7: Sum  -> U (20) -> Merge U-V (20-22)
                # 8: Seat -> W (22) -> Merge W-X (22-24)
                # 9: Mass -> Y (24) -> Merge Y-Z (24-26)
                # 10: Note-> AA(26) -> Merge AA-AD (26-30)
                
                col_map = {
                    0: 'B', 1: 'J', 2: 'K', 3: 'L', 4: 'N',
                    5: 'R', 6: 'S', 7: 'U', 8: 'W', 9: 'Y', 10: 'AA'
                }

                # Ranges (0-based indices, exclusive end)
                merge_list = [
                    (1, 9),      # B-I (Name)
                    (11, 13),    # L-M (Price)
                    (13, 17),    # N-Q (Cost)
                                 # R (Rate - Single, No Merge)
                    (18, 20),    # S-T (VAT Sum)
                    (20, 22),    # U-V (Total w/VAT)
                    (22, 24),    # W-X (Seats)
                    (24, 26),    # Y-Z (Mass)
                    (26, 30)     # AA-AD (Note)
                ]
            else:
                start_addr = "B19"
                sheet_name = "ТН-2"
                # TN-2 Mapping (9 cols) (Assuming user might need shift here too, but sticking to logic until feedback)
                # B-I: (1, 9)
                # L-N: (11, 14) (Price)
                # O-R: (14, 18) (Cost)
                # S: (18, 19) (Rate)
                # T-V: (19, 22) (Sum)
                # W-Z: (22, 26) (CostVAT)
                # AA-AD: (26, 30) (Note)
                merge_list = [
                    (1, 9), (11, 14), (14, 18), 
                    (19, 22), (22, 26), (26, 30)
                ]
            
            if doc_type == "ttn1":
                # Re-build rows for TTN-1
                table_rows = [] 
                counter = 1
                for link in order.product_links:
                    p = link.product
                    qty = link.quantity
                    price = link.price
                    sum_val = price * qty
                    
                    vat_amount = sum_val * 20 / 120
                    price_without_vat = sum_val - vat_amount
                    
                    row_logical = [
                         p.title, "шт.", str(qty), 
                         f"{price:.2f}", f"{sum_val:.2f}", 
                         "без НДС", "-", 
                         f"{sum_val:.2f}", 
                         str(qty), "0.00", "X"
                    ]
                    sparse_row = DocumentService._build_sparse_row(row_logical, col_map, "B")
                    table_rows.append(sparse_row)
                    counter += 1
                
                total_logical = [
                    "ИТОГО", "x", str(total_qty), "x", 
                    f"{total_cost_net:.2f}", "x", 
                    "-", f"{total_cost_gross:.2f}",
                    str(total_qty), "0.00", "X"
                ]
                sparse_total = DocumentService._build_sparse_row(total_logical, col_map, "B")
                table_rows.append(sparse_total)

            link = google_service.generate_sheet(template_id, doc_title, replacements, table_rows, 
                                                 start_cell_addr=start_addr, 
                                                 target_sheet_name=sheet_name,
                                                 merge_cols=merge_list,
                                                 draw_borders=True)
        else:
            # Для остальных - Docs API
            has_footer = (doc_type != "work_order") # Work Order без футера с итогами
            link = google_service.generate_doc(template_id, doc_title, replacements, table_rows, has_footer=has_footer)
            
        return link

    @staticmethod
    def _letter_to_index(letter: str) -> int:
        idx = 0
        for i, c in enumerate(reversed(letter.upper())):
            idx += (ord(c) - 64) * (26 ** i)
        return idx - 1

    @staticmethod
    def _build_sparse_row(logical_values: List[str], col_map: Dict[int, str], start_col_letter: str) -> List[str]:
        """
        Builds a sparse row (with empty strings) to fit specific column letters.
        """
        start_idx = DocumentService._letter_to_index(start_col_letter)
        
        # Determine max index needed
        max_idx = start_idx
        indices = {}
        for logical_idx, letter in col_map.items():
            abs_idx = DocumentService._letter_to_index(letter)
            indices[logical_idx] = abs_idx
            if abs_idx > max_idx: max_idx = abs_idx
            
        row_len = max_idx - start_idx + 1
        sparse_row = [""] * row_len
        
        for logical_idx, val in enumerate(logical_values):
            if logical_idx in indices:
                # Calculate relative position from start_col
                rel_idx = indices[logical_idx] - start_idx
                if 0 <= rel_idx < row_len:
                    sparse_row[rel_idx] = val
                    
        return sparse_row