from datetime import datetime
from typing import Any, List, Optional
from services.google_service import get_google_service
from services.documents.base import BaseDocumentStrategy, TEMPLATES, DOC_NAMES

class GoogleDocStrategy(BaseDocumentStrategy):
    """Base for documents using Google Docs API."""
    
    async def generate(
        self,
        doc_type: str,
        *,
        template_id: Optional[str] = None,
        doc_number: Optional[str] = None,
        document_date: Optional[datetime] = None,
    ) -> str:
        await self.fetch_order()
        if not self.order:
            return "Error: Order not found"

        template_id = template_id or TEMPLATES.get(doc_type)
        if not template_id:
            return f"Error: Template for {doc_type} not found"

        replacements = await self._prepare_base_variables(
            doc_number=doc_number,
            doc_type=doc_type,
            document_date=document_date,
        )
        table_rows = self._prepare_table_data()
        
        # Additional Replacements specific to doc logic
        self._add_specific_replacements(replacements)

        doc_title = f"{DOC_NAMES.get(doc_type, 'Док')} #{self.order.id} {replacements.get('{{client_name}}', '')}"
        
        has_footer = (doc_type != "work_order")
        
        return get_google_service().generate_doc(
            template_id, 
            doc_title, 
            replacements, 
            table_rows, 
            has_footer=has_footer
        )

    def _prepare_table_data(self) -> List[List[str]]:
        """Override in subclasses."""
        return []

    def _add_specific_replacements(self, replacements: dict):
        """Override to add custom tags."""
        pass


class WorkOrderStrategy(GoogleDocStrategy):
    """Наряд-заказ: Equipment list, no price table."""
    
    def _prepare_table_data(self) -> List[List[str]]:
        return [] # No table

    def _add_specific_replacements(self, replacements: dict):
        # Generate equipment list string
        equipment_lines = []
        counter = 1
        for link in self.order.product_links:
            title = link.product.title if link.product else "Оборудование"
            equipment_lines.append(f"{counter}. {title} — {link.quantity} шт.")
            counter += 1
        
        equipment_list_str = "\n".join(equipment_lines)
        replacements["{{equipment_list}}"] = equipment_list_str


class ActStrategy(GoogleDocStrategy):
    """Акт выполненных работ: Services only table."""
    
    def _prepare_table_data(self) -> List[List[str]]:
        table_rows = []
        counter = 1
        for link in self.order.service_links:
            title = link.title or (link.service.title if link.service else "Услуга")
            # 6 columns
            row = [
                str(counter), title, "шт.", 
                str(link.quantity), f"{link.price:.2f}", f"{link.price * link.quantity:.2f}"
            ]
            table_rows.append(row)
            counter += 1
            
        if table_rows:
            total_services = sum(l.price * l.quantity for l in self.order.service_links)
            total_row = ["Всего:", "", "", "", "", f"{total_services:.2f}"]
            table_rows.append(total_row)
            
        return table_rows
    
    def _add_specific_replacements(self, replacements: dict):
        """Добавляем сумму услуг прописью"""
        total_services = sum(l.price * l.quantity for l in self.order.service_links)
        replacements["{{sum_word}}"] = self._amount_in_words(total_services)


class DefectActStrategy(GoogleDocStrategy):
    """Defect/diagnostic act for repair workflow."""

    MONTHS_RU = {
        1: "января",
        2: "февраля",
        3: "марта",
        4: "апреля",
        5: "мая",
        6: "июня",
        7: "июля",
        8: "августа",
        9: "сентября",
        10: "октября",
        11: "ноября",
        12: "декабря",
    }

    @staticmethod
    def _first_text(*values: Any, default: str = "") -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return default

    def _meta_text(self, *keys: str, default: str = "") -> str:
        meta = self.order.technical_meta if self.order and isinstance(self.order.technical_meta, dict) else {}
        repair_meta = meta.get("repair") if isinstance(meta.get("repair"), dict) else {}
        for key in keys:
            text = str(repair_meta.get(key) or "").strip()
            if text:
                return text
            text = str(meta.get(key) or "").strip()
            if text:
                return text
        return default

    def _first_equipment_title(self) -> str:
        if not self.order:
            return ""
        first_link = next(iter(self.order.product_links), None)
        if first_link and first_link.product and first_link.product.title:
            return first_link.product.title
        return self.order.title or ""

    @classmethod
    def _date_text(cls, value: Optional[datetime]) -> str:
        effective = value or datetime.now()
        month = cls.MONTHS_RU.get(effective.month, effective.strftime("%m"))
        return f"{effective.day} {month} {effective.year} г."

    def _add_specific_replacements(self, replacements: dict):
        document_date = datetime.strptime(replacements.get("{{date}}", ""), "%d.%m.%Y") if replacements.get("{{date}}") else datetime.now()
        equipment_name = self._first_text(
            self._meta_text("equipment_name", "defect_equipment_name"),
            self._first_equipment_title(),
            default="кондиционер",
        )
        equipment_brand = self._meta_text("equipment_brand", "brand")
        equipment_model = self._meta_text("equipment_model", "model")
        equipment_power = self._meta_text("equipment_power", "power")
        if equipment_name == "кондиционер":
            detailed_name = " ".join(part for part in [equipment_brand, equipment_model, equipment_power] if part)
            if detailed_name:
                equipment_name = detailed_name
        technical_condition = self._first_text(
            self._meta_text(
                "technical_condition",
                "defect_technical_condition",
                "complaint_official",
                "customer_complaint",
                "complaint_text",
            ),
            getattr(self.order, "measurement_result", None) if self.order else None,
            default="_________________",
        )

        replacements.update(
            {
                "{{defect_act_number}}": replacements.get("{{doc_number}}", replacements.get("{{number}}", "")),
                "{{defect_act_date}}": replacements.get("{{date}}", ""),
                "{{defect_act_date_text}}": self._date_text(document_date),
                "{{equipment_name}}": equipment_name,
                "{{equipment_brand}}": equipment_brand,
                "{{equipment_model}}": equipment_model,
                "{{equipment_power}}": equipment_power,
                "{{equipment_serial_number}}": self._meta_text(
                    "equipment_serial_number",
                    "serial_number",
                    "defect_serial_number",
                    default="_________________",
                ),
                "{{equipment_inventory_number}}": self._meta_text(
                    "equipment_inventory_number",
                    "inventory_number",
                    "defect_inventory_number",
                    default="_________________",
                ),
                "{{equipment_commissioning_date}}": self._meta_text(
                    "equipment_commissioning_date",
                    "commissioning_date",
                    default="_________________",
                ),
                "{{technical_condition}}": technical_condition,
                "{{customer_complaint}}": self._meta_text("customer_complaint", "complaint_text", default="_________________"),
                "{{complaint_official}}": self._meta_text("complaint_official", default="_________________"),
                "{{likely_diagnosis}}": self._meta_text("likely_diagnosis", default="_________________"),
                "{{inspection_work_done}}": self._meta_text(
                    "inspection_work_done",
                    "diagnostic_work_done",
                    default="_________________",
                ),
                "{{startup_check_result}}": self._meta_text(
                    "startup_check_result",
                    "run_check_result",
                    default="_________________",
                ),
                "{{compressor_check_result}}": self._meta_text("compressor_check_result", default="_________________"),
                "{{measurement_result}}": self._meta_text(
                    "measurement_result",
                    "defect_measurement_result",
                    "diagnostic_measurement_result",
                    default=(getattr(self.order, "measurement_result", None) if self.order else None) or "_________________",
                ),
                "{{further_use_assessment}}": self._meta_text(
                    "further_use_assessment",
                    "operation_assessment",
                    default="_________________",
                ),
                "{{operation_restrictions}}": self._meta_text(
                    "operation_restrictions",
                    "use_restrictions",
                    default="_________________",
                ),
                "{{technical_conclusion}}": self._meta_text(
                    "technical_conclusion",
                    "defect_conclusion",
                    default="_________________",
                ),
                "{{repair_feasibility}}": self._meta_text(
                    "repair_feasibility",
                    "repair_feasibility_text",
                    default="_________________",
                ),
                "{{recommended_decision}}": self._meta_text(
                    "recommended_decision",
                    "defect_recommendation",
                    default="_________________",
                ),
            }
        )


class GeneralDocStrategy(GoogleDocStrategy):
    """Contract, Offer, Invoice: Products + Services table."""
    
    def _prepare_table_data(self) -> List[List[str]]:
        table_rows = []
        counter = 1
        
        # Products
        for link in self.order.product_links:
            title = link.product.title if link.product else "Товар"
            row = [
                str(counter), title, "шт.", 
                str(link.quantity), f"{link.price:.2f}", f"{link.price * link.quantity:.2f}"
            ]
            table_rows.append(row)
            counter += 1

        # Services
        for link in self.order.service_links:
            title = link.title or (link.service.title if link.service else "Услуга")
            row = [
                str(counter), title, "шт.", 
                str(link.quantity), f"{link.price:.2f}", f"{link.price * link.quantity:.2f}"
            ]
            table_rows.append(row)
            counter += 1

        if table_rows:
            total_row = ["Всего:", "", "", "", "", f"{self.order.total_amount:.2f}"]
            table_rows.append(total_row)
            
        return table_rows
