from datetime import datetime

import pytest
from sqlmodel import select

from models import (
    Customer,
    CustomerBranch,
    CustomerEquipment,
    CustomerType,
    EquipmentServiceHistory,
    Order,
    OrderStatus,
)
from scripts.repair_equipment_history_backfill_common import (
    RepairOrderBackfillContext,
    apply_backfill_contexts,
    build_backfill_decision,
    build_order_equipment_fingerprint,
    fetch_repair_order_backfill_contexts,
    match_equipment_candidates,
    order_has_repair_meta,
)


def _repair_order(**kwargs):
    defaults = {
        "id": 100,
        "customer_id": 1,
        "customer_branch_id": 10,
        "status": OrderStatus.NEGOTIATION,
        "workflow_type": "repair",
        "updated_at": datetime(2026, 6, 1, 12, 0, 0),
        "technical_meta": {
            "equipment_name": " Кондиционер Daikin ",
            "equipment_serial_number": " SN-001 ",
            "equipment_inventory_number": " INV-001 ",
            "repair": {
                "repair_status": "completed",
                "equipment_model": " FTXB25C ",
                "refrigerant_type": " R32 ",
                "customer_complaint": "Не охлаждает",
            },
        },
    }
    defaults.update(kwargs)
    return Order(tenant_id=1, storefront_id=1, **defaults)


def test_order_equipment_fingerprint_reads_top_level_and_repair_meta_aliases():
    order = _repair_order(technical_meta={
        "equipment_name": " Кондиционер Daikin ",
        "equipment_brand": " Daikin ",
        "equipment_serial_number": " SN-001 ",
        "repair": {
            "repair_status": "completed",
            "equipment_model": " FTXB25C ",
            "equipment_inventory_number": " INV-001 ",
            "refrigerant_type": " R32 ",
        },
    })

    fingerprint = build_order_equipment_fingerprint(order)

    assert order_has_repair_meta(order) is True
    assert fingerprint.equipment_name == "Кондиционер Daikin"
    assert fingerprint.brand == "Daikin"
    assert fingerprint.model == "FTXB25C"
    assert fingerprint.serial == "SN-001"
    assert fingerprint.inventory_number == "INV-001"
    assert fingerprint.refrigerant_type == "R32"


def test_match_equipment_candidates_requires_branch_scope_and_marks_safe_exact_identifier():
    fingerprint = build_order_equipment_fingerprint(_repair_order())
    exact = CustomerEquipment(
        id=1,
        customer_id=1,
        customer_branch_id=10,
        display_name="Daikin FTXB25C",
        brand="Daikin",
        model="FTXB25C",
        serial="sn-001",
    )
    weak = CustomerEquipment(
        id=2,
        customer_id=1,
        customer_branch_id=10,
        display_name="Кондиционер Daikin",
        brand="Daikin",
        model="FTXB25C",
    )
    wrong_branch = CustomerEquipment(
        id=3,
        customer_id=1,
        customer_branch_id=11,
        display_name="Daikin wrong branch",
        serial="SN-001",
    )

    matches = match_equipment_candidates(
        fingerprint=fingerprint,
        equipment_items=[weak, wrong_branch, exact],
        order_branch_id=10,
    )

    assert [match.equipment.id for match in matches] == [1, 2]
    assert matches[0].confidence == "exact-identifier"
    assert matches[0].is_safe_for_backfill is True
    assert matches[1].confidence == "weak-passport"
    assert matches[1].is_safe_for_backfill is False


def test_backfill_decision_skips_existing_history_by_order_id():
    order = _repair_order(id=101)
    context = RepairOrderBackfillContext(
        order=order,
        customer=Customer(tenant_id=1, id=1, name="Owner", phone="+375291111111", type=CustomerType.company),
        branch=CustomerBranch(id=10, customer_id=1, name="Office", delivery_address="Minsk"),
        fingerprint=build_order_equipment_fingerprint(order),
        existing_history=(EquipmentServiceHistory(id=55, equipment_id=9, order_id=101),),
        candidate_matches=(),
    )

    decision = build_backfill_decision(context)

    assert decision.action == "skip-existing-history"
    assert "order_id=101" in decision.reason


def test_backfill_decision_sends_ambiguous_exact_matches_to_manual_review():
    order = _repair_order(id=102)
    fingerprint = build_order_equipment_fingerprint(order)
    equipment_a = CustomerEquipment(id=1, customer_id=1, customer_branch_id=10, serial="SN-001")
    equipment_b = CustomerEquipment(id=2, customer_id=1, customer_branch_id=10, serial="SN-001")
    matches = match_equipment_candidates(
        fingerprint=fingerprint,
        equipment_items=[equipment_a, equipment_b],
        order_branch_id=10,
    )
    context = RepairOrderBackfillContext(
        order=order,
        customer=Customer(tenant_id=1, id=1, name="Owner", phone="+375291111111", type=CustomerType.company),
        branch=CustomerBranch(id=10, customer_id=1, name="Office", delivery_address="Minsk"),
        fingerprint=fingerprint,
        existing_history=(),
        candidate_matches=tuple(matches),
    )

    decision = build_backfill_decision(context)

    assert decision.action == "manual-needed"
    assert "multiple exact" in decision.reason


def test_backfill_decision_auto_creates_only_with_strong_identifier_and_branch_scope():
    order = _repair_order(id=103)
    context = RepairOrderBackfillContext(
        order=order,
        customer=Customer(tenant_id=1, id=1, name="Owner", phone="+375291111111", type=CustomerType.company),
        branch=CustomerBranch(id=10, customer_id=1, name="Office", delivery_address="Minsk"),
        fingerprint=build_order_equipment_fingerprint(order),
        existing_history=(),
        candidate_matches=(),
    )

    decision = build_backfill_decision(context)

    assert decision.action == "create-equipment-and-history"
    assert decision.equipment_payload["customer_branch_id"] == 10
    assert decision.equipment_payload["serial"] == "SN-001"

    no_branch_order = _repair_order(id=104, customer_branch_id=None)
    no_branch_context = RepairOrderBackfillContext(
        order=no_branch_order,
        customer=Customer(tenant_id=1, id=1, name="Owner", phone="+375291111111", type=CustomerType.company),
        branch=None,
        fingerprint=build_order_equipment_fingerprint(no_branch_order),
        existing_history=(),
        candidate_matches=(),
    )

    no_branch_decision = build_backfill_decision(no_branch_context)

    assert no_branch_decision.action == "manual-needed"
    assert "branch scope" in no_branch_decision.reason


@pytest.mark.asyncio
async def test_backfill_dry_run_does_not_create_history(db):
    customer = Customer(tenant_id=1, name="Dry Run Owner", phone="+375291110201", type=CustomerType.company)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    branch = CustomerBranch(customer_id=customer.id, name="Office", delivery_address="Minsk, Test 1")
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    equipment = CustomerEquipment(
        customer_id=customer.id,
        customer_branch_id=branch.id,
        display_name="Daikin FTXB25C",
        serial="SN-DRY-1",
    )
    db.add(equipment)
    await db.commit()
    await db.refresh(equipment)
    order = _repair_order(
        id=None,
        customer_id=customer.id,
        customer_branch_id=branch.id,
        technical_meta={
            "equipment_serial_number": "SN-DRY-1",
            "repair": {"repair_status": "completed", "customer_complaint": "Не охлаждает"},
        },
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    contexts = await fetch_repair_order_backfill_contexts(db, customer_ids={customer.id})
    results = await apply_backfill_contexts(db, contexts, execute=False)

    assert [result.action for result in results] == ["create-history"]
    history_result = await db.execute(
        select(EquipmentServiceHistory).where(EquipmentServiceHistory.order_id == order.id)
    )
    assert history_result.scalars().all() == []


@pytest.mark.asyncio
async def test_backfill_execute_is_idempotent_by_order_id(db):
    customer = Customer(tenant_id=1, name="Repeat Owner", phone="+375291110202", type=CustomerType.company)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    branch = CustomerBranch(customer_id=customer.id, name="Shop", delivery_address="Minsk, Test 2")
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    equipment = CustomerEquipment(
        customer_id=customer.id,
        customer_branch_id=branch.id,
        display_name="Mitsubishi MSZ",
        serial="SN-REPEAT-1",
    )
    db.add(equipment)
    await db.commit()
    await db.refresh(equipment)
    order = _repair_order(
        id=None,
        customer_id=customer.id,
        customer_branch_id=branch.id,
        technical_meta={
            "equipment_serial_number": "SN-REPEAT-1",
            "repair": {
                "repair_status": "completed",
                "customer_complaint": "Плохо холодит",
                "diagnostic_result": "Недостаток хладагента.",
            },
        },
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    first_contexts = await fetch_repair_order_backfill_contexts(db, customer_ids={customer.id})
    first_results = await apply_backfill_contexts(db, first_contexts, execute=True)
    second_contexts = await fetch_repair_order_backfill_contexts(db, customer_ids={customer.id})
    second_results = await apply_backfill_contexts(db, second_contexts, execute=True)

    assert [result.action for result in first_results] == ["create-history"]
    assert first_results[0].executed is True
    assert [result.action for result in second_results] == ["skip-existing-history"]
    history_result = await db.execute(
        select(EquipmentServiceHistory).where(EquipmentServiceHistory.order_id == order.id)
    )
    histories = history_result.scalars().all()
    assert len(histories) == 1
    assert histories[0].equipment_id == equipment.id
