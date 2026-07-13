"""Keeps legacy equipment warranty fields aligned with warranty coverage records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CustomerEquipment, EquipmentWarrantyCoverage


class EquipmentWarrantyBridgeService:
    WARRANTY_FIELDS = {"warranty_started_at", "warranty_expires_at", "warranty_terms"}

    @staticmethod
    def _naive(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @classmethod
    async def sync_manual_fields(
        cls,
        session: AsyncSession,
        *,
        equipment: CustomerEquipment,
        payload: dict[str, Any],
    ) -> EquipmentWarrantyCoverage | None:
        changed_fields = cls.WARRANTY_FIELDS.intersection(payload)
        if not changed_fields:
            return None
        result = await session.execute(
            select(EquipmentWarrantyCoverage).where(
                EquipmentWarrantyCoverage.equipment_id == int(equipment.id or 0),
                EquipmentWarrantyCoverage.component_id.is_(None),
                EquipmentWarrantyCoverage.coverage_type == "supplier",
            )
        )
        coverage = result.scalars().first()
        if coverage and coverage.source not in {"manual", "legacy"}:
            raise ValueError("Warranty dates are managed by the applied coverage; update the coverage instead")

        starts_at = cls._naive(equipment.warranty_started_at)
        expires_at = cls._naive(equipment.warranty_expires_at)
        terms = equipment.warranty_terms
        if coverage is None:
            if starts_at is None and expires_at is None and not terms:
                return None
            coverage = EquipmentWarrantyCoverage(
                equipment_id=int(equipment.id or 0),
                coverage_type="supplier",
                source="manual",
                starts_at=starts_at,
                expires_at=expires_at,
                maintenance_required=False,
                terms_snapshot=terms,
                policy_snapshot={
                    "starts_at": starts_at.isoformat() if starts_at else None,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "terms": terms,
                    "source": "manager_manual",
                },
            )
            session.add(coverage)
            await session.flush()
            return coverage

        previous = {
            "changed_at": datetime.now().isoformat(),
            "starts_at": coverage.starts_at.isoformat() if coverage.starts_at else None,
            "expires_at": coverage.expires_at.isoformat() if coverage.expires_at else None,
            "terms": coverage.terms_snapshot,
            "changed_fields": sorted(changed_fields),
        }
        snapshot = dict(coverage.policy_snapshot or {})
        corrections = list(snapshot.get("manual_corrections") or [])
        corrections.append(previous)
        snapshot.update(
            {
                "starts_at": starts_at.isoformat() if starts_at else None,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "terms": terms,
                "manual_corrections": corrections[-20:],
            }
        )
        coverage.starts_at = starts_at
        coverage.expires_at = expires_at
        coverage.terms_snapshot = terms
        coverage.policy_snapshot = snapshot
        coverage.updated_at = datetime.now()
        session.add(coverage)
        return coverage
