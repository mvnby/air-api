from datetime import datetime
import math
from typing import Any, Dict, List, Optional, Tuple
from num2words import num2words

from services.google_service import get_google_service
from services.documents.base import BaseDocumentStrategy, TEMPLATES, DOC_NAMES

class LogisticsSheetStrategy(BaseDocumentStrategy):
    """Strategy for TN-2 and TTN-1 using Google Sheets API."""

    DEFAULT_COUNTRY = "Китай"
    LOGISTICS_COMPONENT_KINDS = {"indoor", "outdoor", "accessory", "other"}

    async def generate(
        self,
        doc_type: str,
        *,
        template_id: Optional[str] = None,
        doc_number: Optional[str] = None,
        document_date: Optional[datetime] = None,
    ) -> str:
        if not self.order:
            await self.fetch_order()
        if not self.order: return "Order not found"

        template_id = template_id or TEMPLATES.get(doc_type)
        replacements = await self._prepare_base_variables(
            doc_number=doc_number,
            doc_type=doc_type,
            document_date=document_date,
        )
        
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
        
        doc_title = f"{DOC_NAMES.get(doc_type, 'Док')} {doc_number or f'#{self.order.id}'} {replacements.get('{{client_name}}', '')}"
        
        # Config Map
        config = self._get_sheet_config(doc_type)
        
        return get_google_service().generate_sheet(
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
            for component_line in self._expand_product_link_for_logistics(link):
                p = component_line.get("product")
                title = component_line["title"]
                unit = component_line["unit"]
                qty = component_line["quantity"]
                price = component_line["unit_price"]
                cost = component_line["line_total"]
            
                # VAT Logic: Hardcoded "без НДС" for now based on original code.
                cost_with_vat = cost
                vat_rate = "без НДС"

                row_logical = [
                    title,                  # 0
                    unit,                   # 1
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
                        except Exception:
                            pass  # Ignore weight parsing errors

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

    @classmethod
    def _expand_product_link_for_logistics(cls, link: Any) -> List[Dict[str, Any]]:
        product = getattr(link, "product", None)
        product_title = getattr(product, "title", None) or "Товар"
        parent_qty = max(1, int(getattr(link, "quantity", 1) or 1))
        parent_unit_price = float(getattr(link, "price", 0) or 0)
        product_country = cls._product_country(product)

        order_components = cls._normalize_order_components(getattr(link, "logistics_components", None))
        if order_components:
            components = cls._ensure_component_prices(order_components, parent_unit_price)
        else:
            template_components = cls._normalize_product_template_components(product)
            if template_components:
                components = cls._allocate_template_component_prices(template_components, parent_unit_price)
            else:
                components = [
                    {
                        "title": product_title,
                        "country": product_country or cls.DEFAULT_COUNTRY,
                        "unit": "шт.",
                        "quantity_per_parent": 1,
                        "unit_price": parent_unit_price,
                        "kind": None,
                    }
                ]

        rows: List[Dict[str, Any]] = []
        for component in components:
            quantity_per_parent = max(1, int(component.get("quantity_per_parent") or 1))
            qty = parent_qty * quantity_per_parent
            unit_price = float(component.get("unit_price") or 0)
            country = cls._clean_text(component.get("country")) or product_country or cls.DEFAULT_COUNTRY
            title = cls._format_title_with_country(component.get("title") or product_title, country)
            rows.append(
                {
                    "title": title,
                    "unit": cls._clean_text(component.get("unit")) or "шт.",
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": unit_price * qty,
                    "product": product,
                }
            )
        return rows

    @classmethod
    def _normalize_order_components(cls, raw_components: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_components, list):
            return []
        out: List[Dict[str, Any]] = []
        for item in raw_components:
            if not isinstance(item, dict):
                continue
            title = cls._clean_text(item.get("title"))
            if not title:
                continue
            out.append(
                {
                    "title": title,
                    "country": cls._clean_text(item.get("country")),
                    "unit": cls._clean_text(item.get("unit")) or "шт.",
                    "quantity_per_parent": cls._positive_int(item.get("quantity_per_parent"), 1),
                    "unit_price": cls._positive_float(item.get("unit_price"), 0.0),
                    "kind": cls._component_kind(item.get("kind")),
                }
            )
        return out

    @classmethod
    def _normalize_product_template_components(cls, product: Any) -> List[Dict[str, Any]]:
        specs = getattr(product, "specs", None)
        raw_components = specs.get("logistics_components") if isinstance(specs, dict) else None
        if not isinstance(raw_components, list):
            return []
        out: List[Dict[str, Any]] = []
        for item in raw_components:
            if not isinstance(item, dict):
                continue
            title = cls._clean_text(item.get("title"))
            if not title:
                continue
            out.append(
                {
                    "title": title,
                    "country": cls._clean_text(item.get("country")),
                    "unit": cls._clean_text(item.get("unit")) or "шт.",
                    "quantity_per_parent": cls._positive_int(item.get("quantity_per_parent"), 1),
                    "price_weight": cls._positive_float(item.get("price_weight"), 1.0),
                    "kind": cls._component_kind(item.get("kind")),
                }
            )
        return out

    @classmethod
    def _allocate_template_component_prices(
        cls,
        components: List[Dict[str, Any]],
        parent_unit_price: float,
    ) -> List[Dict[str, Any]]:
        weighted = [max(0.0, float(item.get("price_weight") or 0)) for item in components]
        if not any(weighted):
            weighted = [1.0 for _ in components]
        return cls._allocate_component_prices(components, weighted, parent_unit_price)

    @classmethod
    def _ensure_component_prices(
        cls,
        components: List[Dict[str, Any]],
        parent_unit_price: float,
    ) -> List[Dict[str, Any]]:
        per_parent_sum = sum(
            float(item.get("unit_price") or 0) * cls._positive_int(item.get("quantity_per_parent"), 1)
            for item in components
        )
        if per_parent_sum <= 0:
            weights = [1.0 for _ in components]
            return cls._allocate_component_prices(components, weights, parent_unit_price)

        resolved = [dict(item) for item in components]
        diff = parent_unit_price - per_parent_sum
        if abs(diff) >= 0.005 and resolved:
            last = resolved[-1]
            last_qpp = cls._positive_int(last.get("quantity_per_parent"), 1)
            last["unit_price"] = float(last.get("unit_price") or 0) + (diff / last_qpp)
        return resolved

    @classmethod
    def _allocate_component_prices(
        cls,
        components: List[Dict[str, Any]],
        weights: List[float],
        parent_unit_price: float,
    ) -> List[Dict[str, Any]]:
        if not components:
            return []
        total_weight = sum(weights) or float(len(components))
        remaining = parent_unit_price
        resolved: List[Dict[str, Any]] = []
        for idx, item in enumerate(components):
            next_item = dict(item)
            qpp = cls._positive_int(next_item.get("quantity_per_parent"), 1)
            if idx == len(components) - 1:
                component_total = remaining
            else:
                raw_component_total = parent_unit_price * (weights[idx] / total_weight)
                component_total = cls._round_to_nearest_10(raw_component_total)
                remaining -= component_total
            next_item["unit_price"] = component_total / qpp
            resolved.append(next_item)
        return resolved

    @staticmethod
    def _round_to_nearest_10(value: float) -> float:
        return float(math.floor((float(value) + 5) / 10) * 10)

    @classmethod
    def _product_country(cls, product: Any) -> Optional[str]:
        specs = getattr(product, "specs", None)
        if not isinstance(specs, dict):
            return None
        for key in ("country", "country_of_origin", "Страна производства", "Страна-производитель"):
            country = cls._clean_text(specs.get(key))
            if country:
                return country
        return None

    @staticmethod
    def _clean_text(value: Any) -> str:
        return " ".join(str(value or "").split())

    @staticmethod
    def _positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    @staticmethod
    def _positive_float(value: Any, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed >= 0 else default

    @classmethod
    def _component_kind(cls, value: Any) -> Optional[str]:
        kind = cls._clean_text(value)
        return kind if kind in cls.LOGISTICS_COMPONENT_KINDS else None

    @classmethod
    def _format_title_with_country(cls, title: Any, country: str) -> str:
        cleaned_title = cls._clean_text(title) or "Товар"
        normalized_title = cleaned_title.lower().replace("ё", "е")
        if "страна происх" in normalized_title:
            return cleaned_title
        cleaned_country = cls._clean_text(country)
        if not cleaned_country:
            return cleaned_title
        return f"{cleaned_title},\nстрана происх. {cleaned_country}"

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
