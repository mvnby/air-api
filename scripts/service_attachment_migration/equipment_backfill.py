"""Backfill equipment-to-order links and legacy warranty snapshots."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    CustomerEquipment,
    EquipmentOrderLink,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
)
from services.equipment_service import EquipmentService

from .legacy_sources import MigrationStats, _role_from_event


async def migrate_equipment_links(
    session: AsyncSession,
    *,
    execute: bool,
    order_id: int | None,
    stats: MigrationStats,
) -> None:
    pairs: set[tuple[int, int, str]] = set()
    source_stmt = select(CustomerEquipment).where(CustomerEquipment.source_order_id.is_not(None))
    history_stmt = select(EquipmentServiceHistory).where(EquipmentServiceHistory.order_id.is_not(None))
    if order_id is not None:
        source_stmt = source_stmt.where(CustomerEquipment.source_order_id == order_id)
        history_stmt = history_stmt.where(EquipmentServiceHistory.order_id == order_id)
    for equipment in (await session.execute(source_stmt)).scalars().all():
        pairs.add((int(equipment.id or 0), int(equipment.source_order_id or 0), "sale"))
    for event in (await session.execute(history_stmt)).scalars().all():
        role = _role_from_event(event.event_type)
        pairs.add((int(event.equipment_id), int(event.order_id or 0), role))

    for equipment_id, linked_order_id, role in sorted(pairs):
        equipment = await session.get(CustomerEquipment, equipment_id)
        if not equipment:
            stats.equipment_link_conflicts += 1
            stats.issues.append(
                f"equipment-link equipment={equipment_id} order={linked_order_id}: equipment not found"
            )
            continue
        try:
            await EquipmentService._validate_order_link(
                session,
                equipment=equipment,
                order_id=linked_order_id,
            )
        except ValueError as exc:
            stats.equipment_link_conflicts += 1
            stats.issues.append(
                f"equipment-link equipment={equipment_id} order={linked_order_id}: {exc}"
            )
            continue
        existing = await session.scalar(
            select(EquipmentOrderLink.id).where(
                EquipmentOrderLink.equipment_id == equipment_id,
                EquipmentOrderLink.order_id == linked_order_id,
                EquipmentOrderLink.role == role,
            )
        )
        if existing:
            continue
        stats.equipment_links_found += 1
        if execute:
            session.add(
                EquipmentOrderLink(
                    equipment_id=equipment_id,
                    order_id=linked_order_id,
                    role=role,
                )
            )
            stats.equipment_links_created += 1


async def migrate_legacy_coverages(
    session: AsyncSession,
    *,
    execute: bool,
    order_id: int | None,
    stats: MigrationStats,
) -> None:
    stmt = select(CustomerEquipment).where(
        (CustomerEquipment.warranty_started_at.is_not(None))
        | (CustomerEquipment.warranty_expires_at.is_not(None))
    )
    if order_id is not None:
        stmt = stmt.where(CustomerEquipment.source_order_id == order_id)
    for equipment in (await session.execute(stmt)).scalars().all():
        existing = await session.scalar(
            select(EquipmentWarrantyCoverage.id).where(
                EquipmentWarrantyCoverage.equipment_id == int(equipment.id or 0),
                EquipmentWarrantyCoverage.coverage_type == "legacy",
                EquipmentWarrantyCoverage.component_id.is_(None),
            )
        )
        if existing:
            continue
        stats.legacy_coverages_found += 1
        if not execute:
            continue
        session.add(
            EquipmentWarrantyCoverage(
                equipment_id=int(equipment.id or 0),
                coverage_type="legacy",
                source="legacy",
                starts_at=equipment.warranty_started_at,
                expires_at=equipment.warranty_expires_at,
                terms_snapshot=equipment.warranty_terms,
                policy_snapshot={"migration": "customer_equipment_legacy_fields"},
            )
        )
        stats.legacy_coverages_created += 1
