from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import DocumentLegalEntity, DocumentNumberPolicy
from models.tenancy import TenantScope
from modules.documents.domain import (
    DEFAULT_NUMBER_POLICIES,
    EffectiveDocumentNumberPolicy,
)


class DocumentNumberPolicyError(ValueError):
    pass


class DocumentNumberPolicyNotFoundError(DocumentNumberPolicyError):
    pass


@dataclass(frozen=True, slots=True)
class EffectivePolicyItem:
    legal_entity_id: int
    policy: EffectiveDocumentNumberPolicy
    persisted: bool


class DocumentNumberPolicyService:
    @classmethod
    async def list_effective(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
    ) -> list[EffectivePolicyItem]:
        await cls._require_issuer(
            session,
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=legal_entity_id,
        )
        rows = (
            (
                await session.execute(
                    select(DocumentNumberPolicy).where(
                        DocumentNumberPolicy.tenant_id == tenant_scope.tenant_id,
                        DocumentNumberPolicy.legal_entity_id == legal_entity_id,
                        DocumentNumberPolicy.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        persisted = {row.document_type: row for row in rows}
        keys = sorted(set(DEFAULT_NUMBER_POLICIES) | set(persisted))
        return [
            EffectivePolicyItem(
                legal_entity_id=legal_entity_id,
                policy=(
                    EffectiveDocumentNumberPolicy(
                        document_type=persisted[key].document_type,
                        series=persisted[key].series,
                        period_mode=persisted[key].period_mode,
                        minimum_width=persisted[key].minimum_width,
                    ).normalized()
                    if key in persisted
                    else DEFAULT_NUMBER_POLICIES[key]
                ),
                persisted=key in persisted,
            )
            for key in keys
        ]

    @classmethod
    async def get_effective(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        policy_key: str,
    ) -> EffectiveDocumentNumberPolicy:
        normalized_key = str(policy_key or "").strip().lower()
        await cls._require_issuer(
            session,
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=legal_entity_id,
        )
        row = (
            await session.execute(
                select(DocumentNumberPolicy).where(
                    DocumentNumberPolicy.tenant_id == tenant_scope.tenant_id,
                    DocumentNumberPolicy.legal_entity_id == legal_entity_id,
                    DocumentNumberPolicy.document_type == normalized_key,
                    DocumentNumberPolicy.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return EffectiveDocumentNumberPolicy(
                document_type=row.document_type,
                series=row.series,
                period_mode=row.period_mode,
                minimum_width=row.minimum_width,
            ).normalized()
        default = DEFAULT_NUMBER_POLICIES.get(normalized_key)
        if default is None:
            raise DocumentNumberPolicyNotFoundError("Политика нумерации не настроена")
        return default

    @classmethod
    async def upsert(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        document_type: str,
        series: str,
        period_mode: str,
        minimum_width: int,
    ) -> DocumentNumberPolicy:
        effective = EffectiveDocumentNumberPolicy(
            document_type=document_type,
            series=series,
            period_mode=period_mode,
            minimum_width=minimum_width,
        ).normalized()
        await cls._require_issuer(
            session,
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=legal_entity_id,
        )
        row = (
            await session.execute(
                select(DocumentNumberPolicy)
                .where(
                    DocumentNumberPolicy.tenant_id == tenant_scope.tenant_id,
                    DocumentNumberPolicy.legal_entity_id == legal_entity_id,
                    DocumentNumberPolicy.document_type == effective.document_type,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if row is None:
            row = DocumentNumberPolicy(
                tenant_id=tenant_scope.tenant_id,
                legal_entity_id=legal_entity_id,
                document_type=effective.document_type,
                series=effective.series,
                period_mode=effective.period_mode,
                minimum_width=effective.minimum_width,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        else:
            row.series = effective.series
            row.period_mode = effective.period_mode
            row.minimum_width = effective.minimum_width
            row.is_active = True
            row.updated_at = now
        session.add(row)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DocumentNumberPolicyError(
                "Не удалось сохранить политику нумерации"
            ) from exc
        await session.refresh(row)
        return row

    @staticmethod
    async def _require_issuer(
        session: AsyncSession,
        *,
        tenant_id: int,
        legal_entity_id: int,
    ) -> DocumentLegalEntity:
        entity = (
            await session.execute(
                select(DocumentLegalEntity).where(
                    DocumentLegalEntity.id == legal_entity_id,
                    DocumentLegalEntity.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if entity is None:
            raise DocumentNumberPolicyNotFoundError("Юридическое лицо не найдено")
        return entity
