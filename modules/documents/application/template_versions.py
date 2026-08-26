"""Native DOCX template lifecycle commands for the documents module.

Google template rows remain legacy-compatible and are deliberately outside this
service.  These commands manage only immutable ``renderer='docx'`` revisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import re
from typing import Iterable, Mapping
from zipfile import BadZipFile, ZipFile

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import DocumentLegalEntity, DocumentTemplate, DocumentTemplateVersion
from models.tenancy import TenantScope
from modules.documents.infrastructure.renderers import (
    DocumentTemplateVersion as RenderTemplateVersion,
    NativeDocxRenderer,
    TableBlockSpec,
    TemplateValidationResult,
)
from modules.documents.infrastructure.template_source_storage import (
    StoredTemplateSource,
    TemplateSourceStorage,
)


MAX_NATIVE_TEMPLATE_BYTES = 5 * 1024 * 1024
MAX_DOCX_ZIP_ENTRIES = 1_000
MAX_DOCX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
MAX_DOCX_COMPRESSION_RATIO = 100
_PLACEHOLDER_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
_DOC_TYPE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class TemplateVersionError(ValueError):
    pass


class TemplateVersionNotFoundError(TemplateVersionError):
    pass


class TemplateVersionConflictError(TemplateVersionError):
    pass


class TemplateVersionValidationError(TemplateVersionError):
    """Safe validation failure; details are suitable for an editor UI."""

    def __init__(self, result: TemplateValidationResult):
        self.result = result
        super().__init__(
            "; ".join(issue.message for issue in result.issues)
            or "Шаблон не прошёл проверку"
        )


@dataclass(frozen=True, slots=True)
class NativeTemplatePlaceholderContract:
    """Approved scalar fields and repeatable row blocks for one template.

    This is intentionally a declarative whitelist, not a Jinja-like language.
    It serializes into ``DocumentTemplateVersion.placeholder_schema`` unchanged
    enough for later APIs to display and reconstruct the exact contract.
    """

    field_catalog: frozenset[str]
    table_blocks: tuple[TableBlockSpec, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        field_catalog: Iterable[str],
        table_blocks: Iterable[TableBlockSpec | Mapping[str, object]] = (),
    ) -> "NativeTemplatePlaceholderContract":
        fields = tuple(_placeholder_name(value, "Поле") for value in field_catalog)
        if len(fields) != len(set(fields)):
            raise TemplateVersionError("Каталог полей содержит дубли")

        blocks = tuple(_table_block(value) for value in table_blocks)
        names = [block.name for block in blocks]
        if len(names) != len(set(names)):
            raise TemplateVersionError("Блоки таблиц не должны повторяться")
        row_fields = [field for block in blocks for field in block.row_fields]
        if len(row_fields) != len(set(row_fields)):
            raise TemplateVersionError(
                "Поле строки может принадлежать только одному блоку"
            )
        reserved = set(names) | set(row_fields)
        overlap = reserved & set(fields)
        if overlap:
            raise TemplateVersionError(
                "Каталог полей не может включать маркеры таблиц: "
                + ", ".join(sorted(overlap))
            )
        return cls(field_catalog=frozenset(fields), table_blocks=blocks)

    def as_persisted_schema(self) -> dict[str, object]:
        return {
            "fields": sorted(self.field_catalog),
            "tables": [
                {"name": block.name, "row_fields": sorted(block.row_fields)}
                for block in self.table_blocks
            ],
        }


class NativeTemplateVersionService:
    """Commands for tenant/legal-entity-owned native template revisions."""

    @classmethod
    async def create_template(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        name: str,
        doc_type: str,
        description: str | None = None,
    ) -> DocumentTemplate:
        legal_entity_id = _positive_id(legal_entity_id, "legal_entity_id")
        issuer = await cls._get_legal_entity(
            session,
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=legal_entity_id,
        )
        if issuer is None:
            raise TemplateVersionNotFoundError("Юридическое лицо не найдено")
        if issuer.status != "active":
            raise TemplateVersionError(
                "Нельзя создавать шаблон для отключенного юридического лица"
            )

        template = DocumentTemplate(
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=legal_entity_id,
            name=_required_text(name, "Название", 200),
            doc_type=_doc_type(doc_type),
            description=_optional_text(description, 1000),
            google_template_id=None,
            is_active=True,
        )
        session.add(template)
        await cls._commit(session, conflict_message="Не удалось создать шаблон")
        return template

    @classmethod
    async def list_templates(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        doc_type: str | None = None,
    ) -> list[DocumentTemplate]:
        if (
            await cls._get_legal_entity(
                session,
                tenant_id=tenant_scope.tenant_id,
                legal_entity_id=legal_entity_id,
            )
            is None
        ):
            raise TemplateVersionNotFoundError("Юридическое лицо не найдено")
        statement = select(DocumentTemplate).where(
            DocumentTemplate.tenant_id == tenant_scope.tenant_id,
            DocumentTemplate.legal_entity_id == legal_entity_id,
        )
        if doc_type:
            statement = statement.where(
                DocumentTemplate.doc_type == _doc_type(doc_type)
            )
        result = await session.execute(
            statement.order_by(
                DocumentTemplate.doc_type,
                DocumentTemplate.is_default.desc(),
                DocumentTemplate.sort_order,
                DocumentTemplate.name,
                DocumentTemplate.id,
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def upload_native_docx_version(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        template_id: int,
        filename: str,
        content: bytes,
        placeholder_contract: NativeTemplatePlaceholderContract,
        storage: TemplateSourceStorage,
        change_note: str | None = None,
    ) -> DocumentTemplateVersion:
        if not isinstance(placeholder_contract, NativeTemplatePlaceholderContract):
            raise TypeError(
                "placeholder_contract must be NativeTemplatePlaceholderContract"
            )
        if not isinstance(content, bytes) or not content:
            raise TemplateVersionError("Файл шаблона обязателен")
        if len(content) > MAX_NATIVE_TEMPLATE_BYTES:
            raise TemplateVersionError("Размер DOCX шаблона не может превышать 5 МБ")
        preflight_native_docx(content)

        template = await cls._get_scoped_template(
            session,
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=legal_entity_id,
            template_id=template_id,
        )
        await cls._lock_template(session, tenant_scope.tenant_id, int(template.id))
        version_number = await cls._next_version_number(session, int(template.id))
        render_template = RenderTemplateVersion(
            template_key=f"template-{template.id}",
            version=version_number,
            source=content,
            field_catalog=placeholder_contract.field_catalog,
            table_blocks=placeholder_contract.table_blocks,
            filename=filename,
        )
        validation = NativeDocxRenderer().validate(render_template)
        if not validation.is_valid:
            raise TemplateVersionValidationError(validation)

        source = await storage.save(
            tenant_id=tenant_scope.tenant_id,
            template_id=int(template.id),
            version=version_number,
            filename=filename,
            content=content,
        )
        cls._assert_source_matches(
            source, tenant_scope.tenant_id, int(template.id), version_number
        )
        version = DocumentTemplateVersion(
            template_id=int(template.id),
            version=version_number,
            status="draft",
            renderer="docx",
            source_storage_key=source.storage_key,
            source_filename=source.filename,
            checksum_sha256=source.checksum_sha256,
            placeholder_schema=placeholder_contract.as_persisted_schema(),
            change_note=_optional_text(change_note, 1000),
        )
        session.add(version)
        await cls._commit(
            session, conflict_message="Не удалось сохранить новую версию шаблона"
        )
        await session.refresh(version)
        return version

    @classmethod
    async def list_versions(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        template_id: int,
    ) -> list[DocumentTemplateVersion]:
        template = await cls._get_scoped_template(
            session,
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=legal_entity_id,
            template_id=template_id,
        )
        result = await session.execute(
            select(DocumentTemplateVersion)
            .where(DocumentTemplateVersion.template_id == template.id)
            .order_by(DocumentTemplateVersion.version.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_version(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        template_id: int,
        version_id: int,
    ) -> DocumentTemplateVersion:
        template = await cls._get_scoped_template(
            session,
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=legal_entity_id,
            template_id=template_id,
        )
        version = await cls._get_version(
            session,
            template_id=int(template.id),
            version_id=version_id,
        )
        if version is None:
            raise TemplateVersionNotFoundError("Версия шаблона не найдена")
        return version

    @classmethod
    async def activate_version(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        template_id: int,
        version_id: int,
    ) -> DocumentTemplateVersion:
        template = await cls._get_scoped_template(
            session,
            tenant_id=tenant_scope.tenant_id,
            legal_entity_id=legal_entity_id,
            template_id=template_id,
        )
        await cls._lock_template(session, tenant_scope.tenant_id, int(template.id))
        target = await cls._get_version(
            session,
            template_id=int(template.id),
            version_id=version_id,
        )
        if target is None:
            raise TemplateVersionNotFoundError("Версия шаблона не найдена")

        if target.status != "active":
            active_rows = (
                (
                    await session.execute(
                        select(DocumentTemplateVersion)
                        .where(
                            DocumentTemplateVersion.template_id == template.id,
                            DocumentTemplateVersion.status == "active",
                        )
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            for active in active_rows:
                active.status = "retired"
                session.add(active)
            # Flush retirement before activation: the DB's partial unique index
            # remains true even when SQLAlchemy changes statement ordering.
            if active_rows:
                await session.flush()
            target.status = "active"
            target.activated_at = datetime.now(timezone.utc)
            session.add(target)
        await cls._commit(
            session, conflict_message="Не удалось активировать версию шаблона"
        )
        await session.refresh(target)
        return target

    @staticmethod
    async def _get_legal_entity(
        session: AsyncSession,
        *,
        tenant_id: int,
        legal_entity_id: int,
    ) -> DocumentLegalEntity | None:
        return (
            await session.execute(
                select(DocumentLegalEntity).where(
                    DocumentLegalEntity.id == legal_entity_id,
                    DocumentLegalEntity.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def _get_scoped_template(
        cls,
        session: AsyncSession,
        *,
        tenant_id: int,
        legal_entity_id: int,
        template_id: int,
    ) -> DocumentTemplate:
        template_id = _positive_id(template_id, "template_id")
        legal_entity_id = _positive_id(legal_entity_id, "legal_entity_id")
        template = (
            await session.execute(
                select(DocumentTemplate).where(
                    DocumentTemplate.id == template_id,
                    DocumentTemplate.tenant_id == tenant_id,
                    DocumentTemplate.legal_entity_id == legal_entity_id,
                )
            )
        ).scalar_one_or_none()
        if template is None:
            raise TemplateVersionNotFoundError("Шаблон не найден")
        return template

    @staticmethod
    async def _next_version_number(session: AsyncSession, template_id: int) -> int:
        latest = (
            await session.execute(
                select(func.max(DocumentTemplateVersion.version)).where(
                    DocumentTemplateVersion.template_id == template_id
                )
            )
        ).scalar_one()
        return int(latest or 0) + 1

    @staticmethod
    async def _get_version(
        session: AsyncSession,
        *,
        template_id: int,
        version_id: int,
    ) -> DocumentTemplateVersion | None:
        version_id = _positive_id(version_id, "version_id")
        return (
            await session.execute(
                select(DocumentTemplateVersion)
                .where(
                    DocumentTemplateVersion.id == version_id,
                    DocumentTemplateVersion.template_id == template_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _lock_template(
        session: AsyncSession, tenant_id: int, template_id: int
    ) -> None:
        bind = session.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", "") == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)"),
                {"lock_key": f"native_document_template:{tenant_id}:{template_id}"},
            )

    @staticmethod
    async def _commit(session: AsyncSession, *, conflict_message: str) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise TemplateVersionConflictError(conflict_message) from exc

    @staticmethod
    def _assert_source_matches(
        source: StoredTemplateSource, tenant_id: int, template_id: int, version: int
    ) -> None:
        if (source.tenant_id, source.template_id, source.version) != (
            tenant_id,
            template_id,
            version,
        ):
            raise TemplateVersionError(
                "Хранилище вернуло источник из другой области шаблона"
            )


def preflight_native_docx(content: bytes) -> None:
    try:
        with ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            if not infos:
                raise TemplateVersionError("DOCX архив пуст")
            if len(infos) > MAX_DOCX_ZIP_ENTRIES:
                raise TemplateVersionError("DOCX содержит слишком много файлов")
            total_uncompressed = 0
            names: set[str] = set()
            for info in infos:
                name = info.filename
                normalized_path = name.replace("\\", "/")
                path_parts = tuple(part for part in normalized_path.split("/") if part)
                if (
                    not name
                    or "\x00" in name
                    or normalized_path.startswith("/")
                    or normalized_path.startswith("//")
                    or re.match(r"^[a-zA-Z]:/", normalized_path) is not None
                    or any(part == ".." for part in path_parts)
                ):
                    raise TemplateVersionError("DOCX содержит небезопасный путь")
                if info.flag_bits & 0x1:
                    raise TemplateVersionError(
                        "Зашифрованные DOCX шаблоны не поддерживаются"
                    )
                if name in names:
                    raise TemplateVersionError("DOCX содержит повторяющиеся записи")
                names.add(name)
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise TemplateVersionError("Распакованный DOCX слишком большой")
                if info.file_size and (
                    not info.compress_size
                    or info.file_size > info.compress_size * MAX_DOCX_COMPRESSION_RATIO
                ):
                    raise TemplateVersionError(
                        "DOCX имеет небезопасный коэффициент сжатия"
                    )
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise TemplateVersionError("Файл не является DOCX шаблоном")
    except BadZipFile as exc:
        raise TemplateVersionError("Файл не является корректным DOCX архивом") from exc


def _placeholder_name(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not _PLACEHOLDER_NAME.fullmatch(normalized):
        raise TemplateVersionError(f"{label} имеет недопустимое имя")
    return normalized


def _table_block(value: TableBlockSpec | Mapping[str, object]) -> TableBlockSpec:
    if isinstance(value, TableBlockSpec):
        name = value.name
        fields = tuple(value.row_fields)
    elif isinstance(value, Mapping):
        name = value.get("name")
        raw_fields = value.get("row_fields")
        if isinstance(raw_fields, str) or not isinstance(raw_fields, Iterable):
            raise TemplateVersionError("Блок таблицы должен содержать row_fields")
        fields = tuple(raw_fields)
    else:
        raise TemplateVersionError("Блок таблицы имеет неверный формат")
    normalized_name = _placeholder_name(name, "Имя блока")
    if "." in normalized_name:
        raise TemplateVersionError("Имя блока таблицы не может содержать точку")
    normalized_fields = tuple(
        _placeholder_name(field, "Поле строки") for field in fields
    )
    if not normalized_fields or len(normalized_fields) != len(set(normalized_fields)):
        raise TemplateVersionError(
            "Поля блока таблицы должны быть непустыми и уникальными"
        )
    return TableBlockSpec(name=normalized_name, row_fields=frozenset(normalized_fields))


def _positive_id(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise TemplateVersionError(f"{label} должен быть положительным целым числом")
    return value


def _required_text(value: object, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise TemplateVersionError(f"{label} обязательно")
    if len(normalized) > maximum:
        raise TemplateVersionError(f"{label} слишком длинное")
    return normalized


def _optional_text(value: object, maximum: int) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise TemplateVersionError("Значение слишком длинное")
    return normalized


def _doc_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if not _DOC_TYPE.fullmatch(normalized):
        raise TemplateVersionError("Тип документа имеет недопустимый формат")
    return normalized
