from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Literal, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, CustomerBranch, CustomerEquipment, EquipmentServiceHistory, Order
from services.equipment_service import EquipmentService


_SPACE_RE = re.compile(r"\s+")

EQUIPMENT_NAME_KEYS = ("equipment_name", "defect_equipment_name", "display_name")
BRAND_KEYS = ("equipment_brand", "defect_equipment_brand", "brand")
MODEL_KEYS = ("equipment_model", "defect_equipment_model", "model")
SERIAL_KEYS = ("equipment_serial_number", "defect_serial_number", "serial_number", "serial")
INVENTORY_KEYS = ("equipment_inventory_number", "defect_inventory_number", "inventory_number")
EQUIPMENT_TYPE_KEYS = ("equipment_type", "equipment_kind")
REFRIGERANT_KEYS = ("refrigerant_type",)

BackfillAction = Literal[
    "skip-existing-history",
    "create-history",
    "create-equipment-and-history",
    "manual-needed",
]


@dataclass(frozen=True)
class EquipmentFingerprint:
    equipment_name: str | None = None
    brand: str | None = None
    model: str | None = None
    serial: str | None = None
    inventory_number: str | None = None
    equipment_type: str | None = None
    refrigerant_type: str | None = None

    @property
    def has_strong_identifier(self) -> bool:
        return bool(self.serial or self.inventory_number)

    @property
    def has_any_identity_data(self) -> bool:
        return any(
            (
                self.equipment_name,
                self.brand,
                self.model,
                self.serial,
                self.inventory_number,
                self.equipment_type,
                self.refrigerant_type,
            )
        )


@dataclass(frozen=True)
class EquipmentCandidateMatch:
    equipment: CustomerEquipment
    confidence: Literal["exact-identifier", "weak-passport", "conflicting-identifier"]
    reasons: tuple[str, ...]
    branch_scope: Literal["same-branch", "equipment-unassigned", "order-unassigned"]
    conflicts: tuple[str, ...] = ()

    @property
    def is_safe_for_backfill(self) -> bool:
        return self.confidence == "exact-identifier" and not self.conflicts and not bool(self.equipment.is_archived)


@dataclass(frozen=True)
class RepairOrderBackfillContext:
    order: Order
    customer: Customer
    branch: CustomerBranch | None
    fingerprint: EquipmentFingerprint
    existing_history: tuple[EquipmentServiceHistory, ...]
    candidate_matches: tuple[EquipmentCandidateMatch, ...]


@dataclass(frozen=True)
class BackfillDecision:
    action: BackfillAction
    reason: str
    equipment: CustomerEquipment | None = None
    equipment_payload: dict[str, Any] | None = None
    safe_match_count: int = 0


@dataclass(frozen=True)
class BackfillApplyResult:
    order_id: int
    action: BackfillAction
    reason: str
    executed: bool
    equipment_id: int | None = None
    history_id: int | None = None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = _SPACE_RE.sub(" ", str(value)).strip()
    return cleaned or None


def fingerprint_key(value: Any) -> str | None:
    cleaned = clean_text(value)
    return cleaned.casefold() if cleaned else None


def _meta_sources(order: Order) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
    repair_meta = meta.get("repair")
    return meta, repair_meta if isinstance(repair_meta, dict) else {}


def _first_meta_text(sources: Sequence[dict[str, Any]], keys: Iterable[str]) -> str | None:
    for source in sources:
        for key in keys:
            cleaned = clean_text(source.get(key))
            if cleaned:
                return cleaned
    return None


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(clean_text(value))
    if isinstance(value, dict | list | tuple | set):
        return bool(value)
    return True


def order_has_repair_meta(order: Order) -> bool:
    _, repair_meta = _meta_sources(order)
    return any(_has_meaningful_value(value) for value in repair_meta.values())


def build_order_equipment_fingerprint(order: Order) -> EquipmentFingerprint:
    meta, repair_meta = _meta_sources(order)
    sources = (meta, repair_meta)
    return EquipmentFingerprint(
        equipment_name=_first_meta_text(sources, EQUIPMENT_NAME_KEYS),
        brand=_first_meta_text(sources, BRAND_KEYS),
        model=_first_meta_text(sources, MODEL_KEYS),
        serial=_first_meta_text(sources, SERIAL_KEYS),
        inventory_number=_first_meta_text(sources, INVENTORY_KEYS),
        equipment_type=_first_meta_text(sources, EQUIPMENT_TYPE_KEYS),
        refrigerant_type=_first_meta_text(sources, REFRIGERANT_KEYS),
    )


def build_equipment_fingerprint(equipment: CustomerEquipment) -> EquipmentFingerprint:
    return EquipmentFingerprint(
        equipment_name=clean_text(equipment.display_name),
        brand=clean_text(equipment.brand),
        model=clean_text(equipment.model),
        serial=clean_text(equipment.serial),
        inventory_number=clean_text(equipment.inventory_number),
        equipment_type=clean_text(equipment.equipment_type),
        refrigerant_type=clean_text(equipment.refrigerant_type),
    )


def _branch_scope(
    *,
    order_branch_id: int | None,
    equipment_branch_id: int | None,
) -> Literal["same-branch", "equipment-unassigned", "order-unassigned"] | None:
    if order_branch_id is None:
        return "order-unassigned"
    if equipment_branch_id is None:
        return "equipment-unassigned"
    if int(order_branch_id) == int(equipment_branch_id):
        return "same-branch"
    return None


def _matching_fields(order_fp: EquipmentFingerprint, equipment_fp: EquipmentFingerprint) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    conflicts: list[str] = []

    for field_name in ("serial", "inventory_number"):
        order_value = fingerprint_key(getattr(order_fp, field_name))
        equipment_value = fingerprint_key(getattr(equipment_fp, field_name))
        if order_value and equipment_value:
            if order_value == equipment_value:
                reasons.append(field_name)
            else:
                conflicts.append(f"{field_name}_mismatch")

    for field_name in ("brand", "model", "refrigerant_type"):
        order_value = fingerprint_key(getattr(order_fp, field_name))
        equipment_value = fingerprint_key(getattr(equipment_fp, field_name))
        if order_value and equipment_value:
            if order_value == equipment_value:
                reasons.append(field_name)
            else:
                conflicts.append(f"{field_name}_mismatch")

    order_name = fingerprint_key(order_fp.equipment_name)
    equipment_name = fingerprint_key(equipment_fp.equipment_name)
    if order_name and equipment_name and order_name == equipment_name:
        reasons.append("display_name")

    return reasons, conflicts


def match_equipment_candidates(
    *,
    fingerprint: EquipmentFingerprint,
    equipment_items: Iterable[CustomerEquipment],
    order_branch_id: int | None,
) -> list[EquipmentCandidateMatch]:
    matches: list[EquipmentCandidateMatch] = []
    for equipment in equipment_items:
        branch_scope = _branch_scope(
            order_branch_id=order_branch_id,
            equipment_branch_id=equipment.customer_branch_id,
        )
        if branch_scope is None:
            continue

        equipment_fp = build_equipment_fingerprint(equipment)
        reasons, conflicts = _matching_fields(fingerprint, equipment_fp)
        if not reasons:
            continue

        strong_reasons = {"serial", "inventory_number"}.intersection(reasons)
        if strong_reasons and conflicts:
            confidence: Literal["exact-identifier", "weak-passport", "conflicting-identifier"] = "conflicting-identifier"
        elif strong_reasons:
            confidence = "exact-identifier"
        else:
            confidence = "weak-passport"

        matches.append(
            EquipmentCandidateMatch(
                equipment=equipment,
                confidence=confidence,
                reasons=tuple(reasons),
                branch_scope=branch_scope,
                conflicts=tuple(conflicts),
            )
        )

    return sorted(
        matches,
        key=lambda item: (
            0 if item.is_safe_for_backfill else 1,
            item.equipment.customer_branch_id is None,
            item.equipment.id or 0,
        ),
    )


def build_auto_create_equipment_payload(context: RepairOrderBackfillContext) -> dict[str, Any] | None:
    fingerprint = context.fingerprint
    if not fingerprint.has_strong_identifier:
        return None
    if context.order.customer_branch_id is None or context.branch is None:
        return None

    payload = {
        "customer_id": int(context.order.customer_id),
        "customer_branch_id": int(context.order.customer_branch_id),
        "equipment_type": clean_text(fingerprint.equipment_type) or "hvac",
        "display_name": clean_text(fingerprint.equipment_name),
        "brand": clean_text(fingerprint.brand),
        "model": clean_text(fingerprint.model),
        "serial": clean_text(fingerprint.serial),
        "inventory_number": clean_text(fingerprint.inventory_number),
        "refrigerant_type": clean_text(fingerprint.refrigerant_type),
        "notes": f"Auto-created by repair equipment history backfill from order #{context.order.id}.",
    }
    payload["display_name"] = EquipmentService._default_display_name(payload)
    return payload


def build_backfill_decision(context: RepairOrderBackfillContext) -> BackfillDecision:
    if context.existing_history:
        return BackfillDecision(
            action="skip-existing-history",
            reason=f"history already exists for order_id={context.order.id}",
        )

    safe_matches = [match for match in context.candidate_matches if match.is_safe_for_backfill]
    if len(safe_matches) == 1:
        return BackfillDecision(
            action="create-history",
            reason=f"unique exact equipment match by {', '.join(safe_matches[0].reasons)}",
            equipment=safe_matches[0].equipment,
            safe_match_count=1,
        )
    if len(safe_matches) > 1:
        return BackfillDecision(
            action="manual-needed",
            reason=f"multiple exact equipment matches ({len(safe_matches)})",
            safe_match_count=len(safe_matches),
        )
    if context.candidate_matches:
        return BackfillDecision(
            action="manual-needed",
            reason="only weak or conflicting equipment candidates found",
        )

    payload = build_auto_create_equipment_payload(context)
    if payload is not None:
        return BackfillDecision(
            action="create-equipment-and-history",
            reason="no existing candidate; strong passport identifier and branch scope allow auto-create",
            equipment_payload=payload,
        )

    if not context.fingerprint.has_any_identity_data:
        reason = "missing equipment passport data"
    elif not context.fingerprint.has_strong_identifier:
        reason = "missing strong identifier (serial or inventory_number)"
    else:
        reason = "missing branch scope for safe equipment auto-create"
    return BackfillDecision(action="manual-needed", reason=reason)


async def fetch_repair_order_backfill_contexts(
    session: AsyncSession,
    *,
    customer_ids: set[int] | None = None,
    max_orders: int | None = None,
) -> list[RepairOrderBackfillContext]:
    stmt = (
        select(Order, Customer, CustomerBranch)
        .join(Customer, Customer.id == Order.customer_id)
        .outerjoin(CustomerBranch, CustomerBranch.id == Order.customer_branch_id)
        .where(
            Order.workflow_type == "repair",
            Order.customer_id.is_not(None),
        )
        .order_by(Order.updated_at.desc(), Order.created_at.desc(), Order.id.desc())
    )
    if customer_ids:
        stmt = stmt.where(Order.customer_id.in_(sorted(customer_ids)))

    rows = (await session.execute(stmt)).all()
    order_rows: list[tuple[Order, Customer, CustomerBranch | None]] = []
    for order, customer, branch in rows:
        if not order_has_repair_meta(order):
            continue
        order_rows.append((order, customer, branch))
        if max_orders is not None and len(order_rows) >= max(0, int(max_orders)):
            break

    if not order_rows:
        return []

    scoped_customer_ids = {int(order.customer_id) for order, _, _ in order_rows if order.customer_id is not None}
    order_ids = {int(order.id) for order, _, _ in order_rows if order.id is not None}

    equipment_by_customer: dict[int, list[CustomerEquipment]] = defaultdict(list)
    if scoped_customer_ids:
        equipment_result = await session.execute(
            select(CustomerEquipment)
            .where(CustomerEquipment.customer_id.in_(sorted(scoped_customer_ids)))
            .order_by(
                CustomerEquipment.customer_id.asc(),
                CustomerEquipment.customer_branch_id.asc(),
                CustomerEquipment.is_archived.asc(),
                CustomerEquipment.id.asc(),
            )
        )
        for equipment in equipment_result.scalars().all():
            equipment_by_customer[int(equipment.customer_id)].append(equipment)

    history_by_order: dict[int, list[EquipmentServiceHistory]] = defaultdict(list)
    if order_ids:
        history_result = await session.execute(
            select(EquipmentServiceHistory)
            .where(EquipmentServiceHistory.order_id.in_(sorted(order_ids)))
            .order_by(EquipmentServiceHistory.order_id.asc(), EquipmentServiceHistory.id.asc())
        )
        for history in history_result.scalars().all():
            if history.order_id is not None:
                history_by_order[int(history.order_id)].append(history)

    contexts: list[RepairOrderBackfillContext] = []
    for order, customer, branch in order_rows:
        fingerprint = build_order_equipment_fingerprint(order)
        equipment_items = equipment_by_customer.get(int(order.customer_id), [])
        candidate_matches = match_equipment_candidates(
            fingerprint=fingerprint,
            equipment_items=equipment_items,
            order_branch_id=order.customer_branch_id,
        )
        contexts.append(
            RepairOrderBackfillContext(
                order=order,
                customer=customer,
                branch=branch,
                fingerprint=fingerprint,
                existing_history=tuple(history_by_order.get(int(order.id or 0), [])),
                candidate_matches=tuple(candidate_matches),
            )
        )
    return contexts


async def _fetch_existing_history_for_order(
    session: AsyncSession,
    *,
    order_id: int,
) -> list[EquipmentServiceHistory]:
    result = await session.execute(
        select(EquipmentServiceHistory)
        .where(EquipmentServiceHistory.order_id == order_id)
        .order_by(EquipmentServiceHistory.id.asc())
    )
    return list(result.scalars().all())


async def apply_backfill_context(
    session: AsyncSession,
    context: RepairOrderBackfillContext,
    *,
    execute: bool,
) -> BackfillApplyResult:
    decision = build_backfill_decision(context)
    order_id = int(context.order.id)
    equipment_id = int(decision.equipment.id) if decision.equipment and decision.equipment.id is not None else None

    if not execute or decision.action not in {"create-history", "create-equipment-and-history"}:
        return BackfillApplyResult(
            order_id=order_id,
            action=decision.action,
            reason=decision.reason,
            executed=False,
            equipment_id=equipment_id,
        )

    existing_history = await _fetch_existing_history_for_order(session, order_id=order_id)
    if existing_history:
        return BackfillApplyResult(
            order_id=order_id,
            action="skip-existing-history",
            reason=f"history already exists for order_id={order_id}",
            executed=False,
            equipment_id=existing_history[0].equipment_id,
            history_id=existing_history[0].id,
        )

    if decision.action == "create-equipment-and-history":
        assert decision.equipment_payload is not None
        equipment = CustomerEquipment(**decision.equipment_payload)
        session.add(equipment)
        await session.flush()
        await session.refresh(equipment)
    else:
        assert decision.equipment is not None
        equipment = await session.get(CustomerEquipment, int(decision.equipment.id))
        if equipment is None:
            raise RuntimeError(f"Equipment #{decision.equipment.id} disappeared before backfill")

    order = await session.get(Order, order_id)
    if order is None:
        raise RuntimeError(f"Order #{order_id} disappeared before backfill")

    await EquipmentService._validate_order_link(session, equipment=equipment, order_id=order_id)
    history_payload = EquipmentService.build_history_payload_from_repair_order(order)
    history = EquipmentServiceHistory(
        equipment_id=int(equipment.id),
        order_id=history_payload["order_id"],
        event_type=history_payload["event_type"],
        event_date=history_payload["event_date"] or datetime.now(),
        complaint_snapshot=history_payload["complaint_snapshot"],
        diagnostic_result=history_payload["diagnostic_result"],
        repair_recommendation=history_payload["repair_recommendation"],
        refrigerant_type=history_payload["refrigerant_type"],
        refrigerant_amount=history_payload["refrigerant_amount"],
        not_repairable=history_payload["not_repairable"],
        not_repairable_reason=history_payload["not_repairable_reason"],
        notes=history_payload["notes"],
    )
    session.add(history)
    await session.commit()
    await session.refresh(history)

    return BackfillApplyResult(
        order_id=order_id,
        action=decision.action,
        reason=decision.reason,
        executed=True,
        equipment_id=int(equipment.id),
        history_id=int(history.id),
    )


async def apply_backfill_contexts(
    session: AsyncSession,
    contexts: Iterable[RepairOrderBackfillContext],
    *,
    execute: bool,
) -> list[BackfillApplyResult]:
    results: list[BackfillApplyResult] = []
    for context in contexts:
        results.append(await apply_backfill_context(session, context, execute=execute))
    return results


def summarize_results(results: Iterable[BackfillApplyResult]) -> Counter[str]:
    return Counter(result.action for result in results)
