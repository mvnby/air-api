from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from slugify import slugify
from sqlmodel import select

from models import DocumentLegalEntity
from models.tenancy import TenantScope


class DocumentLegalEntityError(ValueError):
    pass


class DocumentLegalEntityConflictError(DocumentLegalEntityError):
    pass


class DocumentLegalEntityNotFoundError(DocumentLegalEntityError):
    pass


class DocumentLegalEntityService:
    """Tenant-scoped issuer configuration used by numbering and templates."""

    @staticmethod
    async def list(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> list[DocumentLegalEntity]:
        result = await session.execute(
            select(DocumentLegalEntity)
            .where(DocumentLegalEntity.tenant_id == tenant_scope.tenant_id)
            .order_by(
                DocumentLegalEntity.is_default.desc(),
                DocumentLegalEntity.status,
                DocumentLegalEntity.display_name,
                DocumentLegalEntity.id,
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        display_name: str,
        slug: str | None,
        legal_name: str | None,
        unp: str | None,
        is_vat_payer: bool,
        is_default: bool,
        requisites: Mapping[str, Any],
    ) -> DocumentLegalEntity:
        normalized_name = cls._required_text(display_name, "Название", 200)
        normalized_slug = cls._slug(slug or normalized_name)
        normalized_legal_name = cls._optional_text(legal_name, 500)
        normalized_unp = cls._optional_text(unp, 32)
        normalized_requisites = cls._requisites(requisites)

        await cls._lock_tenant(session, tenant_scope.tenant_id)
        existing = await cls.list(session, tenant_scope=tenant_scope)
        make_default = bool(is_default or not any(item.is_default for item in existing))
        if make_default:
            await cls._clear_default(session, tenant_scope.tenant_id)

        entity = DocumentLegalEntity(
            tenant_id=tenant_scope.tenant_id,
            slug=normalized_slug,
            display_name=normalized_name,
            legal_name=normalized_legal_name,
            unp=normalized_unp,
            is_vat_payer=bool(is_vat_payer),
            is_default=make_default,
            requisites=normalized_requisites,
            status="active",
        )
        session.add(entity)
        await cls._commit(
            session,
            conflict_message="Юридическое лицо с таким идентификатором уже существует",
        )
        await session.refresh(entity)
        return entity

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        changes: Mapping[str, Any],
    ) -> DocumentLegalEntity:
        await cls._lock_tenant(session, tenant_scope.tenant_id)
        entity = await cls._get_for_update(
            session,
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=legal_entity_id,
        )
        if entity is None:
            raise DocumentLegalEntityNotFoundError("Юридическое лицо не найдено")

        if "display_name" in changes:
            entity.display_name = cls._required_text(
                changes["display_name"], "Название", 200
            )
        if "slug" in changes:
            entity.slug = cls._slug(changes["slug"])
        if "legal_name" in changes:
            entity.legal_name = cls._optional_text(changes["legal_name"], 500)
        if "unp" in changes:
            entity.unp = cls._optional_text(changes["unp"], 32)
        if "is_vat_payer" in changes:
            entity.is_vat_payer = bool(changes["is_vat_payer"])
        if "requisites" in changes:
            entity.requisites = cls._requisites(changes["requisites"] or {})

        requested_status = str(changes.get("status", entity.status)).strip().lower()
        if requested_status not in {"active", "disabled"}:
            raise DocumentLegalEntityError("Недопустимый статус юридического лица")
        wants_default = changes.get("is_default")
        if wants_default is True:
            if requested_status != "active":
                raise DocumentLegalEntityError(
                    "Юридическое лицо по умолчанию должно быть активным"
                )
            await cls._clear_default(
                session, tenant_scope.tenant_id, except_id=legal_entity_id
            )
            entity.is_default = True
        elif wants_default is False and entity.is_default:
            raise DocumentLegalEntityError(
                "Сначала назначьте другое юридическое лицо по умолчанию"
            )
        if requested_status == "disabled" and entity.is_default:
            raise DocumentLegalEntityError(
                "Нельзя отключить юридическое лицо по умолчанию"
            )
        entity.status = requested_status
        entity.updated_at = datetime.now(timezone.utc)
        session.add(entity)
        await cls._commit(
            session,
            conflict_message="Юридическое лицо с таким идентификатором уже существует",
        )
        await session.refresh(entity)
        return entity

    @staticmethod
    async def _get_for_update(
        session: AsyncSession,
        *,
        tenant_id: int,
        legal_entity_id: int,
    ) -> DocumentLegalEntity | None:
        result = await session.execute(
            select(DocumentLegalEntity)
            .where(
                DocumentLegalEntity.id == legal_entity_id,
                DocumentLegalEntity.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _clear_default(
        session: AsyncSession,
        tenant_id: int,
        *,
        except_id: int | None = None,
    ) -> None:
        statement = select(DocumentLegalEntity).where(
            DocumentLegalEntity.tenant_id == tenant_id,
            DocumentLegalEntity.is_default.is_(True),
        )
        if except_id is not None:
            statement = statement.where(DocumentLegalEntity.id != except_id)
        rows = (await session.execute(statement.with_for_update())).scalars().all()
        for row in rows:
            row.is_default = False
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)
        if rows:
            await session.flush()

    @staticmethod
    async def _lock_tenant(session: AsyncSession, tenant_id: int) -> None:
        bind = session.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", "") == "postgresql":
            from sqlalchemy import text

            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)"),
                {"lock_key": f"document_legal_entity:{tenant_id}"},
            )

    @staticmethod
    async def _commit(
        session: AsyncSession,
        *,
        conflict_message: str,
    ) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DocumentLegalEntityConflictError(conflict_message) from exc

    @staticmethod
    def _required_text(value: Any, label: str, maximum: int) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise DocumentLegalEntityError(f"{label} обязательно")
        if len(normalized) > maximum:
            raise DocumentLegalEntityError(f"{label} слишком длинное")
        return normalized

    @staticmethod
    def _optional_text(value: Any, maximum: int) -> str | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        if len(normalized) > maximum:
            raise DocumentLegalEntityError("Значение слишком длинное")
        return normalized

    @staticmethod
    def _slug(value: Any) -> str:
        normalized = slugify(str(value or ""), max_length=80).strip("-")
        if not normalized:
            raise DocumentLegalEntityError("Не удалось сформировать идентификатор")
        return normalized

    @staticmethod
    def _requisites(value: Mapping[str, Any]) -> dict[str, str]:
        if not isinstance(value, Mapping):
            raise DocumentLegalEntityError("Реквизиты должны быть объектом")
        result: dict[str, str] = {}
        for key, raw in value.items():
            normalized_key = str(key or "").strip()
            if not normalized_key:
                continue
            normalized_value = str(raw or "").strip()
            if normalized_value:
                result[normalized_key] = normalized_value
        return result
