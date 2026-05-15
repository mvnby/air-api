from typing import Any, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import RepairComplaintPreset
from schemas import (
    ManagerRepairComplaintPresetCreatePayload,
    ManagerRepairComplaintPresetUpdatePayload,
)


class RepairComplaintService:
    @staticmethod
    def _clean_text(value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @staticmethod
    def _clean_optional(value: Any) -> Optional[str]:
        cleaned = RepairComplaintService._clean_text(value)
        return cleaned or None

    @staticmethod
    async def list_presets(
        session: AsyncSession,
        q: str = "",
        complaint_group: Optional[str] = None,
        include_inactive: bool = False,
        favorites_only: bool = False,
        limit: int = 100,
    ) -> List[RepairComplaintPreset]:
        stmt = select(RepairComplaintPreset)
        if not include_inactive:
            stmt = stmt.where(RepairComplaintPreset.is_active == True)  # noqa: E712
        if favorites_only:
            stmt = stmt.where(RepairComplaintPreset.is_favorite == True)  # noqa: E712
        cleaned_group = RepairComplaintService._clean_text(complaint_group)
        if cleaned_group:
            stmt = stmt.where(RepairComplaintPreset.complaint_group == cleaned_group)
        cleaned_q = RepairComplaintService._clean_text(q)
        if cleaned_q:
            pattern = f"%{cleaned_q}%"
            stmt = stmt.where(
                or_(
                    RepairComplaintPreset.customer_phrase.ilike(pattern),
                    RepairComplaintPreset.document_wording.ilike(pattern),
                    RepairComplaintPreset.likely_diagnosis.ilike(pattern),
                    RepairComplaintPreset.complaint_group.ilike(pattern),
                )
            )
        stmt = stmt.order_by(
            RepairComplaintPreset.is_favorite.desc(),
            RepairComplaintPreset.sort_order,
            RepairComplaintPreset.complaint_group,
            RepairComplaintPreset.customer_phrase,
            RepairComplaintPreset.id,
        ).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def _ensure_not_duplicate(
        session: AsyncSession,
        *,
        complaint_group: str,
        customer_phrase: str,
        exclude_id: Optional[int] = None,
    ) -> None:
        stmt = (
            select(RepairComplaintPreset)
            .where(func.lower(func.trim(RepairComplaintPreset.complaint_group)) == complaint_group.lower())
            .where(func.lower(func.trim(RepairComplaintPreset.customer_phrase)) == customer_phrase.lower())
        )
        if exclude_id is not None:
            stmt = stmt.where(RepairComplaintPreset.id != exclude_id)
        result = await session.execute(stmt.limit(1))
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Repair complaint preset already exists",
            )

    @staticmethod
    async def create_preset(
        session: AsyncSession,
        payload: ManagerRepairComplaintPresetCreatePayload,
    ) -> RepairComplaintPreset:
        customer_phrase = RepairComplaintService._clean_text(payload.customer_phrase)
        if not customer_phrase:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="customer_phrase is required")
        complaint_group = RepairComplaintService._clean_text(payload.complaint_group)
        await RepairComplaintService._ensure_not_duplicate(
            session,
            complaint_group=complaint_group,
            customer_phrase=customer_phrase,
        )
        preset = RepairComplaintPreset(
            complaint_group=complaint_group,
            customer_phrase=customer_phrase,
            document_wording=RepairComplaintService._clean_text(payload.document_wording),
            likely_diagnosis=RepairComplaintService._clean_text(payload.likely_diagnosis),
            is_favorite=bool(payload.is_favorite),
            is_active=bool(payload.is_active),
            sort_order=int(payload.sort_order or 0),
            comment=RepairComplaintService._clean_optional(payload.comment),
        )
        session.add(preset)
        await session.commit()
        await session.refresh(preset)
        return preset

    @staticmethod
    async def update_preset(
        session: AsyncSession,
        preset_id: int,
        payload: ManagerRepairComplaintPresetUpdatePayload,
    ) -> RepairComplaintPreset:
        preset = await session.get(RepairComplaintPreset, preset_id)
        if not preset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair complaint preset not found")

        fields_set = getattr(payload, "model_fields_set", None)
        if fields_set is None:
            fields_set = getattr(payload, "__fields_set__", set())
        next_group = RepairComplaintService._clean_text(
            payload.complaint_group if "complaint_group" in fields_set else preset.complaint_group
        )
        next_phrase = RepairComplaintService._clean_text(
            payload.customer_phrase if "customer_phrase" in fields_set else preset.customer_phrase
        )
        if not next_phrase:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="customer_phrase is required")
        await RepairComplaintService._ensure_not_duplicate(
            session,
            complaint_group=next_group,
            customer_phrase=next_phrase,
            exclude_id=int(preset.id),
        )

        if "complaint_group" in fields_set:
            preset.complaint_group = next_group
        if "customer_phrase" in fields_set:
            preset.customer_phrase = next_phrase
        if "document_wording" in fields_set:
            preset.document_wording = RepairComplaintService._clean_text(payload.document_wording)
        if "likely_diagnosis" in fields_set:
            preset.likely_diagnosis = RepairComplaintService._clean_text(payload.likely_diagnosis)
        if "is_favorite" in fields_set and payload.is_favorite is not None:
            preset.is_favorite = bool(payload.is_favorite)
        if "is_active" in fields_set and payload.is_active is not None:
            preset.is_active = bool(payload.is_active)
        if "sort_order" in fields_set and payload.sort_order is not None:
            preset.sort_order = int(payload.sort_order)
        if "comment" in fields_set:
            preset.comment = RepairComplaintService._clean_optional(payload.comment)

        session.add(preset)
        await session.commit()
        await session.refresh(preset)
        return preset

    @staticmethod
    async def delete_preset(session: AsyncSession, preset_id: int) -> None:
        preset = await session.get(RepairComplaintPreset, preset_id)
        if not preset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair complaint preset not found")
        await session.delete(preset)
        await session.commit()
