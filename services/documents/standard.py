from typing import Any, List
from services.google_service import google_service
from services.documents.base import BaseDocumentStrategy, TEMPLATES, DOC_NAMES

class GoogleDocStrategy(BaseDocumentStrategy):
    """Base for documents using Google Docs API."""
    
    async def generate(self, doc_type: str) -> str:
        await self.fetch_order()
        if not self.order:
            return "Error: Order not found"

        template_id = TEMPLATES.get(doc_type)
        if not template_id:
            return f"Error: Template for {doc_type} not found"

        replacements = self._prepare_base_variables()
        table_rows = self._prepare_table_data()
        
        # Additional Replacements specific to doc logic
        self._add_specific_replacements(replacements)

        doc_title = f"{DOC_NAMES.get(doc_type, 'Док')} #{self.order.id} {replacements.get('{{client_name}}', '')}"
        
        has_footer = (doc_type != "work_order")
        
        return google_service.generate_doc(
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
            title = link.service.title if link.service else "Услуга"
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
            title = link.service.title if link.service else "Услуга"
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
