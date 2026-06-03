from datetime import datetime

import pytest

from models import EquipmentServiceEventType, Order, OrderStatus
from services.equipment_service import EquipmentService


def test_build_history_payload_from_repair_order_maps_repair_meta_fields():
    order = Order(
        id=42,
        status=OrderStatus.NEGOTIATION,
        workflow_type="repair",
        comment="Клиент сообщил о слабом охлаждении.",
        updated_at=datetime(2026, 6, 1, 12, 30, 0),
        technical_meta={
            "repair": {
                "repair_status": "completed",
                "customer_complaint": "Не охлаждает",
                "diagnostic_result": "Выявлена утечка хладагента.",
                "repair_recommendation": "Устранить утечку и дозаправить контур.",
                "refrigerant_type": " R32 ",
                "refrigerant_amount": " 0,45 кг ",
                "repair_completion_note": "Работы выполнены.",
            }
        },
    )

    payload = EquipmentService.build_history_payload_from_repair_order(order)

    assert payload["order_id"] == 42
    assert payload["event_type"] == EquipmentServiceEventType.REPAIR
    assert payload["event_date"] == datetime(2026, 6, 1, 12, 30, 0)
    assert payload["complaint_snapshot"] == "Не охлаждает"
    assert payload["diagnostic_result"] == "Выявлена утечка хладагента."
    assert payload["repair_recommendation"] == "Устранить утечку и дозаправить контур."
    assert payload["refrigerant_type"] == "R32"
    assert payload["refrigerant_amount"] == "0,45 кг"
    assert payload["not_repairable"] is False
    assert payload["notes"] == "Работы выполнены."


def test_build_history_payload_from_repair_order_maps_not_repairable_path():
    order = Order(
        id=43,
        status=OrderStatus.NEGOTIATION,
        workflow_type="repair",
        updated_at=datetime(2026, 6, 2, 9, 0, 0),
        technical_meta={
            "repair": {
                "repair_status": "not_repairable",
                "customer_complaint": "Не запускается",
                "diagnostic_result": "Компрессор не запускается.",
                "repair_possible": "Нет",
                "repair_not_viable_reason": "Стоимость ремонта сопоставима с заменой.",
            }
        },
    )

    payload = EquipmentService.build_history_payload_from_repair_order(order)

    assert payload["event_type"] == EquipmentServiceEventType.NOT_REPAIRABLE
    assert payload["not_repairable"] is True
    assert payload["not_repairable_reason"] == "Стоимость ремонта сопоставима с заменой."


def test_build_history_payload_from_repair_order_rejects_non_repair_order():
    order = Order(status=OrderStatus.NEW_LEAD, workflow_type="sales_installation")

    with pytest.raises(ValueError, match="Only repair orders"):
        EquipmentService.build_history_payload_from_repair_order(order)
