"""Serialize the exact inspected units and their observations into an act snapshot."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from schemas_order_diagnostics import OrderInspectionRevisionItem

if TYPE_CHECKING:
    from schemas_order_sites import OrderSiteEquipmentItem, OrderSiteItem


STATUS_LABELS = {
    "defect_found": "Обнаружен дефект",
    "no_defect_found": "На момент обследования дефект не выявлен",
    "inconclusive": "Для вывода требуется дополнительная диагностика",
    "restored": "Работа восстановлена после указанных действий",
}
COMPONENT_LABELS = {"indoor_unit": "Внутренний блок", "outdoor_unit": "Наружный блок", "drain_pump": "Дренажный насос"}


@dataclass(frozen=True, slots=True)
class OrderTechnicalActScope:
    site: "OrderSiteItem"
    equipment: tuple["OrderSiteEquipmentItem", ...]
    inspections: dict[int, OrderInspectionRevisionItem]
    prepared_by_staff_id: int
    prepared_by: str

    def identifiers(self) -> dict:
        return {
            "site_id": self.site.id,
            "site_ids": [self.site.id],
            "equipment_ids": [item.equipment_id for item in self.equipment],
        }


def describe_equipment(equipment) -> str:
    pieces = [
        equipment.display_name,
        " ".join(part for part in (equipment.brand, equipment.model) if part),
        f"сер. № {equipment.serial}" if equipment.serial else None,
        f"инв. № {equipment.inventory_number}" if equipment.inventory_number else None,
        f"хладагент {equipment.refrigerant_type}" if equipment.refrigerant_type else None,
        equipment.location_hint,
    ]
    return " · ".join(dict.fromkeys(part for part in pieces if part)) or f"Оборудование № {equipment.id}"


def describe_component(component) -> str:
    pieces = [
        component.title or COMPONENT_LABELS.get(component.component_type) or "Компонент",
        " ".join(part for part in (component.brand, component.model) if part),
        f"сер. № {component.serial}" if component.serial else None,
        f"инв. № {component.inventory_number}" if component.inventory_number else None,
    ]
    return " · ".join(dict.fromkeys(part for part in pieces if part))


def extend_technical_act_snapshot(snapshot: dict, scope: OrderTechnicalActScope) -> dict:
    values = {
        key: value for key, value in snapshot["values"].items()
        if key.startswith(("document.", "seller.", "customer.", "order.", "basis."))
    }
    for field, description in (
        ("order.object_address", "адрес объекта"), ("customer.full_name", "наименование заказчика"),
        ("basis.number", "номер договора или предложения"), ("basis.date", "дата основания"),
    ):
        if not str(values.get(field) or "").strip():
            raise ValueError(f"Для технического акта требуется {description}")

    rows = []
    sources = []
    for item in scope.equipment:
        unit = item.equipment
        inspection = scope.inspections[item.equipment_id]
        components = [component for component in unit.components if not component.is_archived]
        equipment = unit.model_dump(mode="json", include={
            "id", "equipment_type", "display_name", "brand", "model", "serial",
            "inventory_number", "location_hint", "refrigerant_type", "installed_at", "commissioned_at",
        })
        equipment["components"] = [
            component.model_dump(mode="json", include={
                "id", "component_type", "title", "brand", "model", "serial", "inventory_number",
            })
            for component in components
        ]
        sources.append({"equipment": equipment, "inspection": inspection.model_dump(mode="json")})
        rows.append({
            "inspection.equipment": "\n".join([describe_equipment(unit), *map(describe_component, components)]),
            "inspection.status": STATUS_LABELS[inspection.status],
            "inspection.facts": inspection.facts,
            "inspection.trial_result": inspection.trial_result or "—",
            "inspection.event_history": inspection.event_history or "—",
            "inspection.recommendations": inspection.recommendations or "—",
            "inspection.performed_actions": inspection.performed_actions or "—",
            "inspection.inspected_at": inspection.inspected_at.strftime("%d.%m.%Y %H:%M %z") if inspection.inspected_at else "—",
            "inspection.performer": inspection.performer or "—",
        })
    snapshot["values"] = values
    snapshot["conditions"] = {
        key: value for key, value in snapshot["conditions"].items()
        if key.startswith(("seller.", "customer.", "order."))
    }
    snapshot["meta"]["draft_parameters"] = {}
    snapshot["meta"]["order_technical_act"] = {
        "schema_version": 1,
        "site": scope.site.model_dump(mode="json", include={"id", "customer_branch_id", "title", "address", "version"}),
        "sources": sources,
        "prepared_by_staff_id": scope.prepared_by_staff_id,
        "prepared_by": scope.prepared_by,
    }
    snapshot["table_rows"] = {"inspections": rows}
    return snapshot
