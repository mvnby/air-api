"""Apply explicit equipment warranty modes without rewriting coverage history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    CustomerEquipment,
    EquipmentServiceEventType,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
    EquipmentWarrantyDecision,
)


class EquipmentWarrantyBridgeService:
    WARRANTY_FIELDS = {
        "warranty_mode",
        "warranty_duration_months",
        "warranty_started_at",
        "warranty_expires_at",
        "warranty_terms",
    }
    NONE_DECISION_REASON = "equipment_warranty_mode_none"
    AUTO_DISABLED_MANUAL_REASON = "manual_coverage_replaced_by_auto"

    @staticmethod
    def _naive(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @classmethod
    async def _equipment_coverages(
        cls, session: AsyncSession, *, equipment_id: int,
    ) -> list[EquipmentWarrantyCoverage]:
        result = await session.execute(
            select(EquipmentWarrantyCoverage)
            .where(
                EquipmentWarrantyCoverage.equipment_id == equipment_id,
                EquipmentWarrantyCoverage.coverage_type.in_({"supplier", "legacy"}),
            )
            .order_by(EquipmentWarrantyCoverage.coverage_type, EquipmentWarrantyCoverage.id)
        )
        return list(result.scalars().all())

    @classmethod
    async def _recalculate_required_due(
        cls,
        session: AsyncSession,
        coverage: EquipmentWarrantyCoverage,
    ) -> None:
        interval = int(coverage.maintenance_interval_months or 0)
        starts_at = cls._naive(coverage.starts_at)
        if not coverage.maintenance_required or interval <= 0 or starts_at is None:
            coverage.next_maintenance_due_at = None
            return
        result = await session.execute(
            select(EquipmentServiceHistory)
            .where(
                EquipmentServiceHistory.equipment_id == coverage.equipment_id,
                EquipmentServiceHistory.event_type == EquipmentServiceEventType.MAINTENANCE,
                EquipmentServiceHistory.event_date >= starts_at,
                EquipmentServiceHistory.maintenance_provider.is_not(None),
            )
            .order_by(EquipmentServiceHistory.event_date.desc(), EquipmentServiceHistory.id.desc())
        )
        required_provider = coverage.allowed_maintenance_provider or "any"
        latest = next(
            (
                item
                for item in result.scalars().all()
                if required_provider == "any" or item.maintenance_provider == required_provider
            ),
            None,
        )
        from services.equipment_service import EquipmentService

        coverage.next_maintenance_due_at = EquipmentService._add_months(
            cls._naive(latest.event_date) if latest else starts_at,
            interval,
        )

    @classmethod
    def _legacy_changed_fields(
        cls,
        equipment: CustomerEquipment,
        payload: dict[str, Any],
        coverage: EquipmentWarrantyCoverage | None = None,
    ) -> set[str]:
        changed: set[str] = set()
        for field in {"warranty_started_at", "warranty_expires_at", "warranty_terms"}.intersection(payload):
            incoming = payload.get(field)
            coverage_field = {
                "warranty_started_at": "starts_at",
                "warranty_expires_at": "expires_at",
                "warranty_terms": "terms_snapshot",
            }[field]
            current = getattr(coverage, coverage_field) if coverage is not None else getattr(equipment, field)
            if field != "warranty_terms":
                incoming = cls._naive(incoming)
                current = cls._naive(current)
            if incoming != current:
                changed.add(field)
        return changed

    @classmethod
    async def _apply_legacy_manual_dates(
        cls,
        session: AsyncSession,
        *,
        equipment: CustomerEquipment,
        coverage: EquipmentWarrantyCoverage,
        payload: dict[str, Any],
        changed_fields: set[str],
        actor: str,
    ) -> EquipmentWarrantyCoverage:
        snapshot = cls._append_snapshot_audit(
            coverage,
            from_mode=equipment.warranty_mode or "auto",
            to_mode="manual",
            actor=actor,
        )
        corrections = list(snapshot.get("manual_corrections") or [])
        corrections.append({
            "changed_at": datetime.now().isoformat(),
            "changed_by": actor,
            "starts_at": cls._iso(cls._naive(coverage.starts_at)),
            "expires_at": cls._iso(cls._naive(coverage.expires_at)),
            "terms": coverage.terms_snapshot,
            "changed_fields": sorted(changed_fields),
        })
        starts_at = cls._naive(payload.get("warranty_started_at", equipment.warranty_started_at))
        expires_at = cls._naive(payload.get("warranty_expires_at", equipment.warranty_expires_at))
        terms = payload.get("warranty_terms", equipment.warranty_terms)
        snapshot.update({
            "manual_override_active": True,
            "manual_starts_at": cls._iso(starts_at),
            "manual_expires_at": cls._iso(expires_at),
            "manual_terms": terms,
            "manual_corrections": corrections[-20:],
        })
        coverage.starts_at = starts_at
        coverage.expires_at = expires_at
        coverage.terms_snapshot = terms
        coverage.policy_snapshot = snapshot
        coverage.updated_at = datetime.now()
        await cls._recalculate_required_due(session, coverage)
        session.add(coverage)
        duration = None
        if starts_at and expires_at:
            candidate = (expires_at.year - starts_at.year) * 12 + expires_at.month - starts_at.month
            from services.equipment_service import EquipmentService

            if candidate > 0 and EquipmentService._add_months(starts_at, candidate) == expires_at:
                duration = candidate
        equipment.warranty_mode = "manual"
        equipment.warranty_duration_months = duration
        equipment.warranty_started_at = starts_at
        equipment.warranty_expires_at = expires_at
        equipment.warranty_terms = terms
        return coverage

    @classmethod
    def _append_snapshot_audit(
        cls,
        coverage: EquipmentWarrantyCoverage,
        *,
        from_mode: str,
        to_mode: str,
        actor: str,
    ) -> dict[str, Any]:
        snapshot = dict(coverage.policy_snapshot or {})
        audit = list(snapshot.get("equipment_warranty_mode_audit") or [])
        audit.append(
            {
                "changed_at": datetime.now().isoformat(),
                "changed_by": actor,
                "from_mode": from_mode,
                "to_mode": to_mode,
                "starts_at": cls._iso(cls._naive(coverage.starts_at)),
                "expires_at": cls._iso(cls._naive(coverage.expires_at)),
                "terms": coverage.terms_snapshot,
            }
        )
        snapshot["equipment_warranty_mode_audit"] = audit[-20:]
        return snapshot

    @classmethod
    async def apply_update(
        cls,
        session: AsyncSession,
        *,
        equipment: CustomerEquipment,
        payload: dict[str, Any],
        actor: str = "manager",
    ) -> EquipmentWarrantyCoverage | None:
        if not cls.WARRANTY_FIELDS.intersection(payload):
            return None

        previous_mode = equipment.warranty_mode or "auto"
        mode = str(payload.get("warranty_mode") or previous_mode)
        if mode not in {"auto", "manual", "none"}:
            raise ValueError("Warranty mode must be auto, manual or none")
        coverages = await cls._equipment_coverages(session, equipment_id=int(equipment.id or 0))
        explicit_mode = "warranty_mode" in payload
        if (
            explicit_mode
            and mode == previous_mode
            and not (cls.WARRANTY_FIELDS - {"warranty_mode"}).intersection(payload)
        ):
            return None
        if not explicit_mode and "warranty_duration_months" not in payload:
            existing_primary = next(
                (item for item in coverages if item.component_id is None and item.coverage_type == "supplier"),
                None,
            )
            if existing_primary is None:
                existing_primary = next(
                    (item for item in coverages if item.component_id is None and item.coverage_type == "legacy"),
                    None,
                )
            legacy_changed_fields = cls._legacy_changed_fields(
                equipment,
                payload,
                existing_primary,
            )
            if not legacy_changed_fields:
                return None
            coverage = existing_primary
            if coverage is None:
                coverage = EquipmentWarrantyCoverage(
                    equipment_id=int(equipment.id or 0),
                    coverage_type="supplier",
                    source="manual",
                    maintenance_required=False,
                    policy_snapshot={"automatic_coverage_before_manual": {"exists": False}},
                )
                session.add(coverage)
                await session.flush()
            elif coverage.source not in {"manual", "legacy"} and previous_mode != "manual":
                raise ValueError("Warranty dates are managed by the applied coverage; switch to manual warranty")
            return await cls._apply_legacy_manual_dates(
                session,
                equipment=equipment,
                coverage=coverage,
                payload=payload,
                changed_fields=legacy_changed_fields,
                actor=actor,
            )

        if mode == "none":
            now = datetime.now()
            for coverage in coverages:
                coverage.policy_snapshot = cls._append_snapshot_audit(
                    coverage, from_mode=previous_mode, to_mode=mode, actor=actor,
                )
                if coverage.decision_status != "voided":
                    coverage.decision_status = "voided"
                    coverage.decision_reason = cls.NONE_DECISION_REASON
                    coverage.decided_at = now
                    coverage.decided_by = actor
                    session.add(EquipmentWarrantyDecision(
                        coverage_id=int(coverage.id or 0), action="voided",
                        reason=cls.NONE_DECISION_REASON, decided_by=actor,
                    ))
                coverage.updated_at = now
                session.add(coverage)
            equipment.warranty_mode = "none"
            equipment.warranty_duration_months = None
            equipment.warranty_started_at = None
            equipment.warranty_expires_at = None
            equipment.warranty_terms = None
            return coverages[0] if coverages else None

        if mode == "auto":
            now = datetime.now()
            for coverage in coverages:
                snapshot = cls._append_snapshot_audit(
                    coverage, from_mode=previous_mode, to_mode=mode, actor=actor,
                )
                original = snapshot.get("automatic_coverage_before_manual")
                if isinstance(original, dict):
                    if original.get("exists", True):
                        coverage.starts_at = datetime.fromisoformat(original["starts_at"]) if original.get("starts_at") else None
                        coverage.expires_at = datetime.fromisoformat(original["expires_at"]) if original.get("expires_at") else None
                        coverage.terms_snapshot = original.get("terms")
                        snapshot["manual_override_active"] = False
                    else:
                        was_already_disabled = (
                            coverage.decision_status == "voided"
                            and coverage.decision_reason == cls.AUTO_DISABLED_MANUAL_REASON
                        )
                        coverage.decision_status = "voided"
                        coverage.decision_reason = cls.AUTO_DISABLED_MANUAL_REASON
                        coverage.decided_at = now
                        coverage.decided_by = actor
                        snapshot["manual_override_active"] = False
                        if not was_already_disabled:
                            session.add(EquipmentWarrantyDecision(
                                coverage_id=int(coverage.id or 0),
                                action="voided",
                                reason=cls.AUTO_DISABLED_MANUAL_REASON,
                                decided_by=actor,
                            ))
                if coverage.decision_status == "voided" and coverage.decision_reason == cls.NONE_DECISION_REASON:
                    coverage.decision_status = "restored"
                    coverage.decision_reason = "equipment_warranty_mode_auto"
                    coverage.decided_at = now
                    coverage.decided_by = actor
                    session.add(EquipmentWarrantyDecision(
                        coverage_id=int(coverage.id or 0), action="restored",
                        reason="equipment_warranty_mode_auto", decided_by=actor,
                    ))
                coverage.policy_snapshot = snapshot
                coverage.updated_at = now
                if coverage.decision_status != "voided":
                    await cls._recalculate_required_due(session, coverage)
                session.add(coverage)
            active = next(
                (item for item in coverages if item.component_id is None and item.decision_status != "voided"),
                None,
            )
            equipment.warranty_mode = "auto"
            equipment.warranty_duration_months = None
            equipment.warranty_started_at = active.starts_at if active else None
            equipment.warranty_expires_at = active.expires_at if active else None
            equipment.warranty_terms = active.terms_snapshot if active else None
            return active

        starts_at = cls._naive(payload.get("warranty_started_at") or equipment.warranty_started_at)
        duration = payload.get("warranty_duration_months", equipment.warranty_duration_months)
        if starts_at is None or duration is None:
            raise ValueError("Manual warranty requires warranty_started_at and warranty_duration_months")
        duration = int(duration)
        if not 1 <= duration <= 240:
            raise ValueError("Warranty duration must be between 1 and 240 months")
        from services.equipment_service import EquipmentService

        expires_at = EquipmentService._add_months(starts_at, duration)
        supplied_expiry = cls._naive(payload.get("warranty_expires_at"))
        if supplied_expiry is not None and supplied_expiry != expires_at:
            raise ValueError("warranty_expires_at must match warranty_started_at plus warranty_duration_months")
        terms = payload.get("warranty_terms", equipment.warranty_terms)
        coverage = next(
            (item for item in coverages if item.component_id is None and item.coverage_type == "supplier"),
            None,
        )
        if coverage is None:
            coverage = next(
                (item for item in coverages if item.component_id is None and item.coverage_type == "legacy"),
                None,
            )
        created_coverage = coverage is None
        if coverage is None:
            coverage = EquipmentWarrantyCoverage(
                equipment_id=int(equipment.id or 0), coverage_type="supplier",
                source="manual", maintenance_required=False,
                policy_snapshot={
                    "source": "manager_manual",
                    "automatic_coverage_before_manual": {"exists": False},
                },
            )
            session.add(coverage)
            await session.flush()
        snapshot = cls._append_snapshot_audit(
            coverage, from_mode=previous_mode, to_mode=mode, actor=actor,
        )
        if "automatic_coverage_before_manual" not in snapshot:
            snapshot["automatic_coverage_before_manual"] = {
                "exists": True,
                "source": coverage.source,
                "policy_id": coverage.policy_id,
                "starts_at": cls._iso(cls._naive(coverage.starts_at)),
                "expires_at": cls._iso(cls._naive(coverage.expires_at)),
                "terms": coverage.terms_snapshot,
            }
        corrections = list(snapshot.get("manual_corrections") or [])
        if not created_coverage:
            corrections.append({
                "changed_at": datetime.now().isoformat(), "changed_by": actor,
                "starts_at": cls._iso(cls._naive(coverage.starts_at)),
                "expires_at": cls._iso(cls._naive(coverage.expires_at)),
                "terms": coverage.terms_snapshot,
            })
        snapshot.update({
            "manual_override_active": True,
            "manual_starts_at": cls._iso(starts_at),
            "manual_expires_at": cls._iso(expires_at),
            "manual_duration_months": duration,
            "manual_terms": terms,
            "manual_corrections": corrections[-20:],
        })
        coverage.starts_at = starts_at
        coverage.expires_at = expires_at
        coverage.terms_snapshot = terms
        coverage.policy_snapshot = snapshot
        if coverage.decision_status == "voided" and coverage.decision_reason in {
            cls.NONE_DECISION_REASON,
            cls.AUTO_DISABLED_MANUAL_REASON,
        }:
            coverage.decision_status = "restored"
            coverage.decision_reason = "equipment_warranty_mode_manual"
            coverage.decided_at = datetime.now()
            coverage.decided_by = actor
            session.add(EquipmentWarrantyDecision(
                coverage_id=int(coverage.id or 0), action="restored",
                reason="equipment_warranty_mode_manual", decided_by=actor,
            ))
        coverage.updated_at = datetime.now()
        await cls._recalculate_required_due(session, coverage)
        session.add(coverage)
        equipment.warranty_mode = "manual"
        equipment.warranty_duration_months = duration
        equipment.warranty_started_at = starts_at
        equipment.warranty_expires_at = expires_at
        equipment.warranty_terms = terms
        return coverage

    @classmethod
    async def sync_manual_fields(
        cls, session: AsyncSession, *, equipment: CustomerEquipment, payload: dict[str, Any],
    ) -> EquipmentWarrantyCoverage | None:
        """Backward-compatible entry point for legacy callers."""
        legacy_payload = dict(payload)
        legacy_payload.setdefault("warranty_mode", "manual")
        if legacy_payload.get("warranty_duration_months") is None:
            starts = cls._naive(legacy_payload.get("warranty_started_at") or equipment.warranty_started_at)
            expires = cls._naive(legacy_payload.get("warranty_expires_at") or equipment.warranty_expires_at)
            if starts and expires:
                legacy_payload["warranty_duration_months"] = max(
                    1, (expires.year - starts.year) * 12 + expires.month - starts.month,
                )
        return await cls.apply_update(session, equipment=equipment, payload=legacy_payload)
