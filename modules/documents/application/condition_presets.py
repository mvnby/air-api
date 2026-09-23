"""Tenant-scoped library of reusable document clauses."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import DocumentConditionPreset
from models.tenancy import TenantScope


class ConditionPresetError(ValueError):
    pass


class ConditionPresetNotFound(ConditionPresetError):
    pass


class ConditionPresetService:
    @staticmethod
    async def list(session: AsyncSession, scope: TenantScope) -> list[DocumentConditionPreset]:
        result = await session.execute(
            select(DocumentConditionPreset)
            .where(DocumentConditionPreset.tenant_id == scope.tenant_id)
            .order_by(DocumentConditionPreset.created_at.desc(), DocumentConditionPreset.id.desc())
            .limit(100)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(session: AsyncSession, scope: TenantScope, text: str) -> DocumentConditionPreset:
        cleaned = text.strip()
        normalized = " ".join(cleaned.split()).casefold()
        if not cleaned or len(cleaned) > 1000 or len(normalized) > 1000:
            raise ConditionPresetError("Условие должно содержать от 1 до 1000 символов")
        row = DocumentConditionPreset(tenant_id=scope.tenant_id, text=cleaned, normalized_text=normalized)
        session.add(row)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ConditionPresetError("Такое условие уже сохранено") from exc
        await session.refresh(row)
        return row

    @staticmethod
    async def delete(session: AsyncSession, scope: TenantScope, preset_id: int) -> None:
        row = await session.get(DocumentConditionPreset, preset_id)
        if row is None or row.tenant_id != scope.tenant_id:
            raise ConditionPresetNotFound("Условие не найдено")
        await session.delete(row)
        await session.commit()
