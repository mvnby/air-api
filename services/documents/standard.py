import re
from datetime import datetime
from typing import Any, List, Optional
from sqlmodel import select
from services.google_service import get_google_service
from services.documents.base import BaseDocumentStrategy, TEMPLATES, DOC_NAMES
from services.repair_defect_template_service import RepairDefectTemplateService
from models import CustomerContract, CustomerEquipment, EquipmentComponent, OrderDocument

class GoogleDocStrategy(BaseDocumentStrategy):
    """Base for documents using Google Docs API."""
    
    async def generate(
        self,
        doc_type: str,
        *,
        template_id: Optional[str] = None,
        doc_number: Optional[str] = None,
        document_date: Optional[datetime] = None,
        base_document: Optional[OrderDocument] = None,
        base_customer_contract: Optional[CustomerContract] = None,
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
            base_document=base_document,
            base_customer_contract=base_customer_contract,
        )
        table_rows = self._prepare_table_data()
        
        # Additional Replacements specific to doc logic
        self._add_specific_replacements(replacements)
        self._append_placeholder_aliases(replacements)

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

    @staticmethod
    def _is_explicit_negative_repair_text(value: Any) -> bool:
        text = str(value or "").strip().lower()
        if not text:
            return False
        return any(
            marker in text
            for marker in (
                "невозмож",
                "не возмож",
                "нецелесообраз",
                "не целесообраз",
                "нерентаб",
                "не рентаб",
                "списан",
                "списани",
                "вывести из эксплуатации",
            )
        )

    @staticmethod
    def _bool_text(value: Any) -> str:
        if isinstance(value, bool):
            return "Да" if value else "Нет"
        return ""

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

    def _meta_value(self, key: str) -> Any:
        meta = self.order.technical_meta if self.order and isinstance(self.order.technical_meta, dict) else {}
        repair_meta = meta.get("repair") if isinstance(meta.get("repair"), dict) else {}
        if key in repair_meta:
            return repair_meta.get(key)
        return meta.get(key)

    def _repair_meta(self) -> dict[str, Any]:
        meta = self.order.technical_meta if self.order and isinstance(self.order.technical_meta, dict) else {}
        repair_meta = meta.get("repair") if isinstance(meta.get("repair"), dict) else {}
        return repair_meta

    def _repair_possible_text(self, default: str = "") -> str:
        canonical = self._meta_value("repair_possible")
        bool_text = self._bool_text(canonical)
        if bool_text:
            return bool_text
        canonical_text = self._first_text(canonical)
        if canonical_text:
            return canonical_text

        legacy = self._meta_value("repair_feasibility")
        bool_text = self._bool_text(legacy)
        if bool_text:
            return bool_text
        legacy_text = self._first_text(legacy)
        if legacy_text and not self._is_explicit_negative_repair_text(legacy_text):
            return legacy_text
        return default

    def _repair_not_viable_text(self, default: str = "") -> str:
        canonical = self._meta_value("repair_not_viable")
        bool_text = self._bool_text(canonical)
        if bool_text:
            return bool_text
        canonical_text = self._first_text(canonical)
        if canonical_text:
            return canonical_text

        legacy = self._meta_value("repair_feasibility")
        if isinstance(legacy, bool):
            return "Нет" if legacy else "Да"
        legacy_text = self._first_text(legacy)
        if legacy_text and self._is_explicit_negative_repair_text(legacy_text):
            return legacy_text
        return default

    def _repair_not_viable_reason_text(self, default: str = "") -> str:
        canonical = self._meta_text("repair_not_viable_reason")
        if canonical:
            return canonical
        legacy = self._meta_value("repair_feasibility")
        legacy_text = self._first_text(legacy)
        if legacy_text and self._is_explicit_negative_repair_text(legacy_text):
            return legacy_text
        return default

    def _first_equipment_title(self) -> str:
        if not self.order:
            return ""
        first_link = next(iter(self.order.product_links), None)
        if first_link and first_link.product and first_link.product.title:
            return first_link.product.title
        return self.order.title or ""

    @staticmethod
    def _clean_equipment_model(value: Any) -> str:
        if isinstance(value, dict):
            value = next(
                (value.get(key) for key in ("model", "equipment_model", "name") if value.get(key)),
                "",
            )
        text = re.sub(
            r"\b(?:внутренний|наружный)\s+блок\b",
            " ",
            str(value or "").strip(),
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\(\s*\)|\[\s*\]|\{\s*\}", " ", text)
        return re.sub(r"\s+", " ", text).strip(" \t:;,/|—–-")

    def _equipment_models(self) -> list[str]:
        raw_models = self._meta_value("equipment_models")
        values = raw_models if isinstance(raw_models, (list, tuple)) else []
        if not values:
            values = [self._meta_text("equipment_model", "model")]

        models: list[str] = []
        seen: set[str] = set()
        for value in values:
            model = self._clean_equipment_model(value)
            identity = model.casefold()
            if not model or identity in seen:
                continue
            seen.add(identity)
            models.append(model)
        return models

    @staticmethod
    def _without_leading_brand(model: str, brand: str) -> str:
        if not brand:
            return model
        match = re.match(re.escape(brand), model, flags=re.IGNORECASE)
        if not match:
            return model
        remainder = model[match.end():]
        if remainder and not (remainder[0].isspace() or remainder[0] in ":;,/|—–-"):
            return model
        return remainder.lstrip(" \t:;,/|—–-")

    def _format_equipment_name(self, brand: str, models: list[str]) -> str:
        if not brand and not models:
            equipment_name = self._clean_equipment_model(
                self._meta_text("equipment_name", "defect_equipment_name")
            )
            fallback = equipment_name or self._clean_equipment_model(self._first_equipment_title())
            generic_markers = ("ремонт", "диагностик", "сервис", "заявк", "заказ")
            if fallback.casefold() == "оборудование" or any(
                marker in fallback.casefold() for marker in generic_markers
            ):
                fallback = ""
            if not fallback:
                return "Кондиционер"
            if fallback.casefold().startswith("кондиционер"):
                return fallback[0].upper() + fallback[1:]
            return f"Кондиционер {fallback}"

        unique_models: list[str] = []
        seen: set[str] = set()
        for model in models:
            model_without_brand = self._without_leading_brand(model, brand)
            identity = model_without_brand.casefold()
            if not model_without_brand or identity in seen:
                continue
            seen.add(identity)
            unique_models.append(model_without_brand)

        details = " ".join(part for part in (brand, " / ".join(unique_models)) if part)
        return f"Кондиционер {details}" if details else "Кондиционер"

    @classmethod
    def _date_text(cls, value: Optional[datetime]) -> str:
        effective = value or datetime.now()
        month = cls.MONTHS_RU.get(effective.month, effective.strftime("%m"))
        return f"{effective.day} {month} {effective.year} г."

    def _add_specific_replacements(self, replacements: dict):
        document_date = datetime.strptime(replacements.get("{{date}}", ""), "%d.%m.%Y") if replacements.get("{{date}}") else datetime.now()
        equipment_brand = self._meta_text("equipment_brand", "brand")
        equipment_models = self._equipment_models()
        equipment_model = " / ".join(equipment_models)
        equipment_name = self._format_equipment_name(equipment_brand, equipment_models)
        equipment_power = self._meta_text("equipment_power", "power")
        generated_repair_meta = RepairDefectTemplateService.build_document_fields(self._repair_meta())
        technical_condition = self._first_text(
            self._meta_text("technical_condition", "defect_technical_condition"),
            generated_repair_meta.get("technical_condition"),
            self._meta_text("complaint_official", "customer_complaint", "complaint_text"),
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
                "{{customer_complaint}}": self._meta_text(
                    "customer_complaint",
                    "complaint_official",
                    "complaint_text",
                    default="_________________",
                ),
                "{{complaint_official}}": self._meta_text("complaint_official", default="_________________"),
                "{{likely_diagnosis}}": self._meta_text("likely_diagnosis", default="_________________"),
                "{{inspection_work_done}}": self._meta_text(
                    "inspection_work_done",
                    "diagnostic_work_done",
                    default=generated_repair_meta.get("inspection_work_done") or "_________________",
                ),
                "{{startup_check_result}}": self._meta_text(
                    "startup_check_result",
                    "run_check_result",
                    default="_________________",
                ),
                "{{compressor_check_result}}": self._meta_text("compressor_check_result", default="_________________"),
                "{{measurement_result}}": self._meta_text(
                    "measurement_result",
                    "inspection_work_done",
                    "defect_measurement_result",
                    "diagnostic_measurement_result",
                    default=generated_repair_meta.get("measurement_result")
                    or self._meta_text("diagnostic_result")
                    or (getattr(self.order, "measurement_result", None) if self.order else None)
                    or "_________________",
                ),
                "{{diagnostic_result}}": self._meta_text(
                    "diagnostic_result",
                    "measurement_result",
                    "defect_measurement_result",
                    "diagnostic_measurement_result",
                    default=(
                        getattr(self.order, "measurement_result", None) if self.order else None
                    ) or generated_repair_meta.get("diagnostic_result") or "_________________",
                ),
                "{{further_use_assessment}}": self._meta_text(
                    "further_use_assessment",
                    "operation_assessment",
                    default=generated_repair_meta.get("further_use_assessment") or "_________________",
                ),
                "{{operation_restrictions}}": self._meta_text(
                    "operation_restrictions",
                    "use_restrictions",
                    default=generated_repair_meta.get("operation_restrictions") or "_________________",
                ),
                "{{technical_conclusion}}": self._meta_text(
                    "technical_conclusion",
                    "defect_conclusion",
                    "repair_recommendation",
                    "recommended_decision",
                    default=generated_repair_meta.get("technical_conclusion") or "_________________",
                ),
                "{{repair_feasibility}}": self._meta_text(
                    "repair_feasibility",
                    "repair_feasibility_text",
                    default=generated_repair_meta.get("repair_feasibility") or self._repair_possible_text(default="_________________"),
                ),
                "{{recommended_decision}}": self._meta_text(
                    "recommended_decision",
                    "defect_recommendation",
                    "repair_recommendation",
                    "technical_conclusion",
                    default=generated_repair_meta.get("recommended_decision") or "_________________",
                ),
                "{{repair_recommendation}}": self._meta_text(
                    "repair_recommendation",
                    "recommended_decision",
                    "defect_recommendation",
                    "technical_conclusion",
                    "defect_conclusion",
                    default=generated_repair_meta.get("repair_recommendation") or "_________________",
                ),
                "{{repair_possible}}": self._repair_possible_text(
                    default=generated_repair_meta.get("repair_possible") or "_________________"
                ),
                "{{repair_status}}": self._meta_text("repair_status", default="_________________"),
                "{{customer_approval_status}}": self._meta_text(
                    "customer_approval_status",
                    default="_________________",
                ),
                "{{customer_approval_note}}": self._meta_text("customer_approval_note", default="_________________"),
                "{{parts_status}}": self._meta_text("parts_status", default="_________________"),
                "{{parts_note}}": self._meta_text("parts_note", default="_________________"),
                "{{repair_completion_note}}": self._meta_text("repair_completion_note", default="_________________"),
                "{{refrigerant_type}}": self._meta_text(
                    "refrigerant_type",
                    default=generated_repair_meta.get("refrigerant_type") or "_________________",
                ),
                "{{refrigerant_amount}}": self._meta_text(
                    "refrigerant_amount",
                    default=generated_repair_meta.get("refrigerant_amount") or "_________________",
                ),
                "{{refrigerant_pricing_mode}}": self._meta_text("refrigerant_pricing_mode", default="_________________"),
                "{{repair_not_viable}}": self._repair_not_viable_text(default="_________________"),
                "{{repair_not_viable_reason}}": self._repair_not_viable_reason_text(default="_________________"),
            }
        )


class B2CDocumentStrategy(GoogleDocStrategy):
    """Retail receipt and service act for individual customers."""

    MONTHS_RU_GENITIVE = {
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
    def _money(value: Any) -> str:
        return f"{float(value or 0):.2f}".replace(".", ",")

    @staticmethod
    def _quantity(value: Any) -> str:
        number = float(value or 0)
        return str(int(number)) if number.is_integer() else str(number).replace(".", ",")

    @classmethod
    def _date_text(cls, value: datetime) -> str:
        month = cls.MONTHS_RU_GENITIVE.get(value.month, value.strftime("%m"))
        return f"{value.day:02d} {month} {value.year} г."

    @staticmethod
    def _line_title(link: Any, fallback: str) -> str:
        title = str(getattr(link, "title", "") or "").strip()
        if title:
            return title
        item = getattr(link, "product", None) or getattr(link, "service", None)
        return str(getattr(item, "title", "") or fallback).strip() or fallback

    @staticmethod
    def _line_total(link: Any) -> float:
        return float(getattr(link, "price", 0) or 0) * float(getattr(link, "quantity", 0) or 0)

    @classmethod
    def _join_titles(cls, links: list[Any], fallback: str) -> str:
        titles = [cls._line_title(link, fallback) for link in links]
        return "\n".join(titles)

    @classmethod
    def _sum_amount(cls, links: list[Any]) -> float:
        return sum(cls._line_total(link) for link in links)

    @classmethod
    def _sum_quantity(cls, links: list[Any]) -> str:
        quantity = sum(float(getattr(link, "quantity", 0) or 0) for link in links)
        return cls._quantity(quantity)

    @classmethod
    def _unit_price_text(cls, links: list[Any]) -> str:
        if len(links) != 1:
            return ""
        return cls._money(getattr(links[0], "price", 0))

    def _prepare_table_data(self) -> List[List[str]]:
        # B2C templates have custom table layouts; they are filled via placeholders.
        return []

    def _add_specific_replacements(self, replacements: dict):
        effective_date = datetime.strptime(replacements.get("{{date}}", ""), "%d.%m.%Y") if replacements.get("{{date}}") else datetime.now()
        product_links = list(getattr(self.order, "product_links", []) or [])
        service_links = list(getattr(self.order, "service_links", []) or [])
        total_amount = float(getattr(self.order, "total_amount", 0) or 0)
        product_total = self._sum_amount(product_links)
        service_total = self._sum_amount(service_links)
        customer = getattr(self.order, "customer", None)

        primary_product = self._line_title(product_links[0], "кондиционер / сплит-система") if product_links else "кондиционер / сплит-система"
        service_lines = service_links or []
        if not service_lines and not product_links:
            fallback_title = str(getattr(self.order, "title", "") or "Работы / услуги").strip()
            service_text = fallback_title
            service_total = total_amount
            service_quantity = "1"
            service_price = self._money(total_amount)
        else:
            service_text = self._join_titles(service_lines, "Услуга")
            service_quantity = self._sum_quantity(service_lines) if service_lines else ""
            service_price = self._unit_price_text(service_lines)

        replacements.update(
            {
                "{{offer_url}}": "https://mvn.by/offer/",
                "{{base_document_type}}": "Публичная оферта",
                "{{base_document_number}}": "https://mvn.by/offer/",
                "{{base_document_date}}": self._date_text(effective_date),
                "{{date_text}}": self._date_text(effective_date),
                "{{date_day}}": f"{effective_date.day:02d}",
                "{{date_month}}": self.MONTHS_RU_GENITIVE.get(effective_date.month, effective_date.strftime("%m")),
                "{{date_year}}": str(effective_date.year),
                "{{client_phone}}": str(getattr(customer, "phone", "") or ""),
                "{{customer_phone}}": str(getattr(customer, "phone", "") or ""),
                "{{equipment_primary}}": primary_product,
                "{{equipment_list}}": self._join_titles(product_links, "Оборудование") or primary_product,
                "{{receipt_product_lines}}": self._join_titles(product_links, "Товар"),
                "{{receipt_product_qty}}": self._sum_quantity(product_links) if product_links else "",
                "{{receipt_product_price}}": self._unit_price_text(product_links),
                "{{receipt_product_total}}": self._money(product_total) if product_links else "",
                "{{receipt_service_lines}}": service_text,
                "{{receipt_service_qty}}": service_quantity,
                "{{receipt_service_price}}": service_price,
                "{{receipt_service_total}}": self._money(service_total) if service_text else "",
                "{{receipt_total}}": self._money(total_amount),
                "{{receipt_total_in_words}}": self._amount_in_words(total_amount),
                "{{service_act_lines}}": service_text,
                "{{service_act_total}}": self._money(service_total or total_amount),
                "{{service_act_total_in_words}}": self._amount_in_words(service_total or total_amount),
            }
        )


class WarrantyCertificateStrategy(B2CDocumentStrategy):
    """Warranty certificate based on equipment created from an order."""

    @staticmethod
    def _format_date(value: Optional[datetime]) -> str:
        return value.strftime("%d.%m.%Y") if value else ""

    @staticmethod
    def _component_title(component: EquipmentComponent) -> str:
        return " ".join(
            part
            for part in [
                component.title,
                component.brand,
                component.model,
                f"SN {component.serial}" if component.serial else "",
            ]
            if str(part or "").strip()
        ) or "Блок оборудования"

    async def _prepare_base_variables(self, *args, **kwargs) -> dict[str, str]:
        replacements = await super()._prepare_base_variables(*args, **kwargs)
        if not self.order or self.order.id is None:
            return replacements

        equipment_result = await self.session.execute(
            select(CustomerEquipment)
            .where(
                CustomerEquipment.source_order_id == self.order.id,
                CustomerEquipment.is_archived == False,
            )
            .order_by(CustomerEquipment.id.asc())
        )
        equipment_items = list(equipment_result.scalars().all())
        equipment_ids = [int(item.id) for item in equipment_items if item.id is not None]
        components_by_equipment: dict[int, list[EquipmentComponent]] = {equipment_id: [] for equipment_id in equipment_ids}
        if equipment_ids:
            component_result = await self.session.execute(
                select(EquipmentComponent)
                .where(
                    EquipmentComponent.equipment_id.in_(equipment_ids),
                    EquipmentComponent.is_archived == False,
                )
                .order_by(EquipmentComponent.equipment_id.asc(), EquipmentComponent.component_type.asc(), EquipmentComponent.id.asc())
            )
            for component in component_result.scalars().all():
                components_by_equipment.setdefault(int(component.equipment_id), []).append(component)

        equipment_lines: list[str] = []
        component_lines: list[str] = []
        serial_lines: list[str] = []
        warranty_until = ""
        for index, equipment in enumerate(equipment_items, start=1):
            title = " ".join(
                part
                for part in [
                    equipment.display_name,
                    equipment.brand,
                    equipment.model,
                    f"SN {equipment.serial}" if equipment.serial else "",
                ]
                if str(part or "").strip()
            ) or f"Оборудование #{equipment.id}"
            equipment_lines.append(f"{index}. {title}")
            if equipment.warranty_expires_at and not warranty_until:
                warranty_until = self._format_date(equipment.warranty_expires_at)
            components = components_by_equipment.get(int(equipment.id or 0), [])
            for component in components:
                component_lines.append(f"{index}. {self._component_title(component)}")
                if component.serial:
                    serial_lines.append(f"{component.title or component.component_type}: {component.serial}")

        replacements.update(
            {
                "{{warranty_equipment_list}}": "\n".join(equipment_lines),
                "{{warranty_component_list}}": "\n".join(component_lines),
                "{{warranty_serial_list}}": "\n".join(serial_lines),
                "{{warranty_started_at}}": (
                    self._format_date(equipment_items[0].warranty_started_at) if equipment_items else ""
                ),
                "{{warranty_expires_at}}": warranty_until,
                "{{warranty_terms}}": "\n".join(
                    item.warranty_terms for item in equipment_items if str(item.warranty_terms or "").strip()
                ),
            }
        )
        return replacements


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
