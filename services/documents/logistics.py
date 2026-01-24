from typing import List, Dict, Tuple
from num2words import num2words

from services.google_service import google_service
from services.documents.base import BaseDocumentStrategy, TEMPLATES, DOC_NAMES

class LogisticsSheetStrategy(BaseDocumentStrategy):
    """Strategy for TN-2 and TTN-1 using Google Sheets API."""

    async def generate(self, doc_type: str) -> str:
        await self.fetch_order()
        if not self.order: return "Order not found"

        template_id = TEMPLATES.get(doc_type)
        replacements = await self._prepare_base_variables(doc_number=None, doc_type=doc_type)
        
        # Add TTN specific empty placeholders if TTN-1
        if doc_type == "ttn1":
             replacements.update({
                 "{{car_model}}": "-",
                 "{{car_number}}": "-",
                 "{{driver_name}}": "-",
                 "{{carrier}}": "-"
             })

        # Calculate Totals & Rows
        table_rows, totals = self._prepare_sheet_data(doc_type)
        
        # Enriched Replacements with Totals
        replacements.update(totals)
        
        doc_title = f"{DOC_NAMES.get(doc_type, 'Док')} #{self.order.id} {replacements.get('{{client_name}}', '')}"
        
        # Config Map
        config = self._get_sheet_config(doc_type)
        
        return google_service.generate_sheet(
            template_id, 
            doc_title, 
            replacements, 
            table_rows, 
            start_cell_addr=config['start_addr'], 
            target_sheet_name=config['sheet_name'],
            merge_cols=config['merge_list'],
            draw_borders=True
        )

    def _get_sheet_config(self, doc_type: str) -> dict:
        if doc_type == "ttn1":
            return {
                "start_addr": "B22",
                "sheet_name": "ТТН-1",
                # 0:Name, 1:Unit, 2:Qty, 3:Price, 4:Cost, 5:Rate, 6:VAT, 7:Sum, 8:Seat, 9:Mass, 10:Note
                "col_map": {
                    0: 'B', 1: 'J', 2: 'K', 3: 'L', 4: 'N',
                    5: 'R', 6: 'S', 7: 'U', 8: 'W', 9: 'Y', 10: 'AA'
                },
                "merge_list": [
                    (1, 9),      # B-I (Name)
                    (11, 13),    # L-M (Price)
                    (13, 17),    # N-Q (Cost)
                    (18, 20),    # S-T (VAT Sum)
                    (20, 22),    # U-V (Total w/VAT)
                    (22, 24),    # W-X (Seats)
                    (24, 26),    # Y-Z (Mass)
                    (26, 30)     # AA-AD (Note)
                ]
            }
        else:
             # TN-2
             return {
                "start_addr": "B19",
                "sheet_name": "ТН-2",
                # 0:Name, 1:Unit, 2:Qty, 3:Price, 4:Cost, 5:Rate, 6:VAT, 7:Sum, 8:Note
                "col_map": {
                    0: 'B', 1: 'J', 2: 'K', 3: 'L', 4: 'O', 
                    5: 'S', 6: 'T', 7: 'W', 8: 'AA'
                },
                "merge_list": [
                    (1, 9), (11, 14), (14, 18), 
                    (19, 22), (22, 26), (26, 30)
                ]
            }

    def _prepare_sheet_data(self, doc_type: str) -> Tuple[List[List[str]], Dict[str, str]]:
        table_rows = []
        is_ttn1 = (doc_type == "ttn1")
        config = self._get_sheet_config(doc_type)
        col_map = config['col_map']
        start_col = config['start_addr'][0] # 'B'

        total_qty = 0
        total_cost_net = 0.0
        total_cost_gross = 0.0
        total_weight = 0.0
        
        # Rows
        for link in self.order.product_links:
            p = link.product
            title = p.title if p else "Товар"
            qty = link.quantity
            price = link.price
            cost = price * qty
            
            # VAT Logic: Hardcoded "без НДС" for now based on original code
            # Wait, original TTN1 specific logic:
            # vat_amount = sum_val * 20 / 120 ?
            # Lines 362 in original: `vat_amount = sum_val * 20 / 120` BUT `vat_rate` is "без НДС".
            # The original code at line 362 calculates `vat_amount` but effectively uses "без НДС" text in column.
            # And `price_without_vat` is calculated but `cost` (which is `sum_val`) is used in col 4 (N).
            # Wait, line 367 uses `sum_val` (gross) in column 4?
            # Original code:
            # TN2:  Col 4(O) = cost (price*qty). Col 7(W) = cost_with_vat (=cost).
            # TTN1: Col 4(N) = sum_val (price*qty). Col 7(U) = sum_val.
            # So effectively Price = Gross Price, VAT = 0.
            
            cost_with_vat = cost 
            vat_rate = "без НДС"

            row_logical = [
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
                row_logical.extend([str(qty), "0.00", "X"]) # 8, 9, 10 (Seats, Mass, Note)
            else:
                row_logical.append("X") # 8 (Note)

            sparse_row = self._build_sparse_row(row_logical, col_map, start_col)
            table_rows.append(sparse_row)

            total_qty += qty
            total_cost_net += cost
            total_cost_gross += cost_with_vat
            
            # Weight calc
            if p and p.specs:
                 spec_w = p.specs.get("weight") or p.specs.get("weight_net") or p.specs.get("вес")
                 if spec_w:
                     try:
                        total_weight += (float(spec_w) * qty)
                     except Exception: pass  # Ignore weight parsing errors

        # Total Row
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
                 
            sparse_total = self._build_sparse_row(total_logical, col_map, start_col)
            table_rows.append(sparse_total)

        # Totals Dict
        totals_map = {
            "{{total_qty}}": str(total_qty),
            "{{total_vat}}": "0.00",
            "{{total_with_vat_words}}": self._amount_in_words(total_cost_gross),
            "{{total_qty_words}}": num2words(total_qty, lang='ru'),
            "{{total_weight}}": f"{total_weight:.2f}",
            "{{total_weight_words}}": num2words(total_weight, lang='ru')
        }
        
        # Services Sum Words (For Footer if needed, though usually TN2/TTN are products only)
        # But we should preserve the logic just in case
        total_services_sum = sum(l.price * l.quantity for l in self.order.service_links)
        try:
             services_word_val = num2words(total_services_sum, lang='ru', to='currency', currency='RUB')
        except Exception:
             services_word_val = f"{total_services_sum:.2f}"
        
        totals_map["{{total_services_word}}"] = services_word_val.capitalize()
        totals_map["{{sum_word}}"] = totals_map["{{total_services_word}}"] # Fallback

        return table_rows, totals_map

    @staticmethod
    def _letter_to_index(letter: str) -> int:
        idx = 0
        for i, c in enumerate(reversed(letter.upper())):
            idx += (ord(c) - 64) * (26 ** i)
        return idx - 1

    @staticmethod
    def _build_sparse_row(logical_values: List[str], col_map: Dict[int, str], start_col_letter: str) -> List[str]:
        start_idx = LogisticsSheetStrategy._letter_to_index(start_col_letter)
        
        # Determine max index needed
        max_idx = start_idx
        indices = {}
        for logical_idx, letter in col_map.items():
            abs_idx = LogisticsSheetStrategy._letter_to_index(letter)
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
