from datetime import datetime

import pytest

from models import EquipmentServiceEventType, EquipmentServiceHistory, Order, OrderStatus
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


@pytest.mark.parametrize(
    ("repair_status", "expected"),
    [
        ("completed", True),
        ("not_repairable", True),
        ("cancelled", False),
        ("diagnostic_in_progress", False),
        ("awaiting_customer_approval", False),
    ],
)
def test_repair_order_history_sync_eligibility_policy_is_terminal_only(repair_status, expected):
    order = Order(
        status=OrderStatus.NEGOTIATION,
        workflow_type="repair",
        technical_meta={"repair": {"repair_status": repair_status}},
    )

    assert EquipmentService.is_repair_order_history_sync_eligible(order) is expected


def test_repair_order_history_sync_eligibility_rejects_non_repair_order():
    order = Order(
        status=OrderStatus.NEW_LEAD,
        workflow_type="sales_installation",
        technical_meta={"repair": {"repair_status": "completed"}},
    )

    assert EquipmentService.is_repair_order_history_sync_eligible(order) is False


def test_resolve_repair_order_history_sync_target_returns_same_equipment_history():
    history = EquipmentServiceHistory(id=7, equipment_id=3, order_id=42)

    result = EquipmentService.resolve_repair_order_history_sync_target(
        [history],
        equipment_id=3,
        order_id=42,
    )

    assert result is history


def test_resolve_repair_order_history_sync_target_rejects_other_equipment_history():
    history = EquipmentServiceHistory(id=8, equipment_id=4, order_id=42)

    with pytest.raises(ValueError, match="already belongs to equipment #4"):
        EquipmentService.resolve_repair_order_history_sync_target(
            [history],
            equipment_id=3,
            order_id=42,
        )
