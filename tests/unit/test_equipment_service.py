from datetime import datetime, timedelta

import pytest

from models import (
    CustomerEquipment,
    EquipmentServiceEventType,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
    Order,
    OrderStatus,
)
from services.equipment_service import EquipmentService


def test_warranty_status_uses_equipment_warranty_dates():
    now = datetime.now()

    assert EquipmentService._warranty_status(CustomerEquipment(customer_id=1)) == "none"
    assert EquipmentService._warranty_status(
        CustomerEquipment(customer_id=1, warranty_started_at=now - timedelta(days=1))
    ) == "unknown"
    assert EquipmentService._warranty_status(
        CustomerEquipment(customer_id=1, warranty_started_at=now - timedelta(days=1), warranty_expires_at=now + timedelta(days=1))
    ) == "active"
    assert EquipmentService._warranty_status(
        CustomerEquipment(customer_id=1, warranty_started_at=now - timedelta(days=3), warranty_expires_at=now - timedelta(days=1))
    ) == "expired"
    assert EquipmentService._warranty_status(
        CustomerEquipment(customer_id=1, warranty_started_at=now + timedelta(days=1), warranty_expires_at=now + timedelta(days=3))
    ) == "scheduled"


def test_coverage_summary_replaces_stale_legacy_warranty_fields():
    now = datetime(2026, 7, 13, 12, 0)
    data = EquipmentService._to_equipment_item(
        CustomerEquipment(
            customer_id=1,
            warranty_started_at=datetime(2020, 1, 1),
            warranty_expires_at=datetime(2021, 1, 1),
            warranty_terms="Old legacy value",
        )
    )
    supplier = EquipmentWarrantyCoverage(
        equipment_id=1,
        coverage_type="supplier",
        starts_at=datetime(2026, 7, 1),
        expires_at=datetime(2028, 7, 1),
        terms_snapshot="Supplier snapshot",
    )
    work = EquipmentWarrantyCoverage(
        equipment_id=1,
        coverage_type="mvn_work",
        starts_at=datetime(2026, 7, 1),
        expires_at=datetime(2027, 7, 1),
        terms_snapshot="Work snapshot",
    )

    EquipmentService._apply_coverage_summary(data, [work, supplier], now=now)

    assert data["warranty_status"] == "active"
    assert data["warranty_started_at"] == datetime(2026, 7, 1)
    assert data["warranty_expires_at"] == datetime(2028, 7, 1)
    assert data["warranty_terms"] == "Supplier snapshot"


def test_add_months_clamps_month_end_for_warranty_expiry():
    assert EquipmentService._add_months(datetime(2026, 1, 31, 10, 0, 0), 1) == datetime(2026, 2, 28, 10, 0, 0)
    assert EquipmentService._add_months(datetime(2026, 2, 28, 10, 0, 0), 12) == datetime(2027, 2, 28, 10, 0, 0)


def test_normalize_component_type_accepts_known_split_blocks():
    assert EquipmentService._normalize_component_type(" indoor_unit ") == "indoor_unit"
    assert EquipmentService._normalize_component_type("outdoor_unit") == "outdoor_unit"
    assert EquipmentService._normalize_component_type(None) == "other"


def test_normalize_component_type_rejects_unknown_values():
    with pytest.raises(ValueError, match="Invalid component_type"):
        EquipmentService._normalize_component_type("compressor")


def test_build_history_payload_from_repair_order_maps_repair_meta_fields():
    order = Order(
        tenant_id=1,
        storefront_id=1,
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
        tenant_id=1,
        storefront_id=1,
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
    order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, workflow_type="sales_installation")

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
        tenant_id=1,
        storefront_id=1,
        status=OrderStatus.NEGOTIATION,
        workflow_type="repair",
        technical_meta={"repair": {"repair_status": repair_status}},
    )

    assert EquipmentService.is_repair_order_history_sync_eligible(order) is expected


def test_repair_order_history_sync_eligibility_rejects_non_repair_order():
    order = Order(
        tenant_id=1,
        storefront_id=1,
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
