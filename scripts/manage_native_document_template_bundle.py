#!/usr/bin/env python3
"""Plan or idempotently apply a native DOCX template bundle.

The manifest is safe to version in Git; tenant-owned DOCX bytes remain outside
the repository and are written directly to private template storage on apply.
No template or historical version is deleted by this command.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePath
import re
from typing import Any, AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.database import async_session_maker, engine
from models import DocumentLegalEntity, DocumentTemplate, DocumentTemplateVersion
from models.tenancy import Storefront, Tenant, TenantScope
from modules.documents.application.template_versions import (
    NativeTemplatePlaceholderContract,
    NativeTemplateVersionService,
    preflight_native_docx,
)
from modules.documents.domain import (
    CONDITIONAL_FLAGS,
    LINE_ROW_PLACEHOLDERS,
    PAYMENT_SCHEDULE_ROW_PLACEHOLDERS,
    SCALAR_PLACEHOLDERS,
    SUPPORTED_NATIVE_DOCUMENT_TYPES,
)
from modules.documents.infrastructure.renderers import NativeDocxRenderer, TableBlockSpec
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTRACT_SCENARIOS = {
    "services",
    "repair",
    "maintenance",
    "supply_installation",
    "installation",
    "framework",
    "supply",
}
_BUSINESS_ROLES = {"payment_request", "offer"}


class BundleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    key: str
    name: str
    aliases: tuple[str, ...]
    doc_type: str
    source_filename: str
    checksum_sha256: str
    description: str | None
    sort_order: int
    contract_scenario: str | None = None
    business_role: str | None = None


@dataclass(frozen=True, slots=True)
class BundleSpec:
    bundle_id: str
    description: str | None
    templates: tuple[TemplateSpec, ...]


@dataclass(frozen=True, slots=True)
class PreparedSource:
    content: bytes
    contract: NativeTemplatePlaceholderContract


def load_bundle(path: Path) -> BundleSpec:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"Не удалось прочитать манифест: {exc}") from exc
    if not isinstance(payload, dict):
        raise BundleError("Манифест должен быть JSON-объектом")
    bundle_id = _required_text(payload.get("bundle_id"), "bundle_id", 120)
    raw_templates = payload.get("templates")
    if not isinstance(raw_templates, list) or not raw_templates:
        raise BundleError("Манифест должен содержать непустой список templates")
    templates = tuple(_template_spec(item) for item in raw_templates)
    keys = [item.key for item in templates]
    if len(keys) != len(set(keys)):
        raise BundleError("Ключи шаблонов в пакете должны быть уникальными")
    identities = [(item.doc_type, item.name.casefold()) for item in templates]
    if len(identities) != len(set(identities)):
        raise BundleError("Названия шаблонов одного типа должны быть уникальными")
    return BundleSpec(
        bundle_id=bundle_id,
        description=_optional_text(payload.get("description"), 1000),
        templates=templates,
    )


def prepare_sources(bundle: BundleSpec, source_dir: Path) -> dict[str, PreparedSource]:
    prepared: dict[str, PreparedSource] = {}
    for spec in bundle.templates:
        source_path = source_dir / spec.source_filename
        try:
            content = source_path.read_bytes()
        except OSError as exc:
            raise BundleError(f"Не удалось прочитать {spec.source_filename}: {exc}") from exc
        actual_checksum = sha256(content).hexdigest()
        if actual_checksum != spec.checksum_sha256:
            raise BundleError(
                f"Контрольная сумма {spec.source_filename} не совпадает: "
                f"ожидалась {spec.checksum_sha256}, получена {actual_checksum}"
            )
        preflight_native_docx(content)
        prepared[spec.key] = PreparedSource(
            content=content,
            contract=_discover_contract(content),
        )
    return prepared


async def inspect_bundle(
    session: AsyncSession,
    *,
    tenant_id: int,
    legal_entity_id: int,
    bundle: BundleSpec,
) -> tuple[TenantScope, list[dict[str, Any]]]:
    scope = await _tenant_scope(session, tenant_id=tenant_id)
    issuer = (
        await session.execute(
            select(DocumentLegalEntity).where(
                DocumentLegalEntity.id == legal_entity_id,
                DocumentLegalEntity.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if issuer is None or issuer.status != "active":
        raise BundleError("Активное юридическое лицо пакета не найдено")

    plan: list[dict[str, Any]] = []
    for spec in bundle.templates:
        template = await _matching_template(
            session,
            tenant_id=tenant_id,
            legal_entity_id=legal_entity_id,
            spec=spec,
        )
        active_checksum = None
        if template is not None:
            active_checksum = (
                await session.execute(
                    select(DocumentTemplateVersion.checksum_sha256).where(
                        DocumentTemplateVersion.template_id == template.id,
                        DocumentTemplateVersion.status == "active",
                    )
                )
            ).scalar_one_or_none()
        metadata_changes = _metadata_changes(template, spec)
        plan.append(
            {
                "key": spec.key,
                "doc_type": spec.doc_type,
                "template_id": template.id if template else None,
                "template_action": "create" if template is None else (
                    "update" if metadata_changes else "keep"
                ),
                "metadata_changes": metadata_changes,
                "version_action": (
                    "keep" if active_checksum == spec.checksum_sha256 else "upload_activate"
                ),
                "source_filename": spec.source_filename,
                "sha256": spec.checksum_sha256,
            }
        )
    return scope, plan


async def apply_bundle(
    session: AsyncSession,
    *,
    scope: TenantScope,
    legal_entity_id: int,
    bundle: BundleSpec,
    prepared: dict[str, PreparedSource],
) -> list[dict[str, Any]]:
    from modules.documents.api.router import get_private_attachment_storage

    storage = PrivateTemplateSourceStorage(get_private_attachment_storage())
    results: list[dict[str, Any]] = []
    for spec in bundle.templates:
        try:
            result = await _apply_bundle_item(
                session,
                scope=scope,
                legal_entity_id=legal_entity_id,
                bundle=bundle,
                spec=spec,
                source=prepared[spec.key],
                storage=storage,
            )
        except Exception as exc:
            raise BundleError(
                f"Пакет применён частично до {spec.key}. Устраните причину и "
                "безопасно повторите тот же apply: уже совпавшие версии будут пропущены. "
                f"Причина: {exc}"
            ) from exc
        results.append(result)
    return results


async def _apply_bundle_item(
    session: AsyncSession,
    *,
    scope: TenantScope,
    legal_entity_id: int,
    bundle: BundleSpec,
    spec: TemplateSpec,
    source: PreparedSource,
    storage: PrivateTemplateSourceStorage,
) -> dict[str, Any]:
    template = await _matching_template(
        session,
        tenant_id=scope.tenant_id,
        legal_entity_id=legal_entity_id,
        spec=spec,
    )
    created = template is None
    if template is None:
        template = await NativeTemplateVersionService.create_template(
            session,
            tenant_scope=scope,
            legal_entity_id=legal_entity_id,
            name=spec.name,
            doc_type=spec.doc_type,
            description=spec.description,
            contract_scenario=spec.contract_scenario,
            business_role=spec.business_role,
        )
    changed = _apply_metadata(template, spec)
    if changed:
        session.add(template)
        await session.commit()
        await session.refresh(template)

    active_checksum = (
        await session.execute(
            select(DocumentTemplateVersion.checksum_sha256).where(
                DocumentTemplateVersion.template_id == template.id,
                DocumentTemplateVersion.status == "active",
            )
        )
    ).scalar_one_or_none()
    version_id = None
    uploaded = active_checksum != spec.checksum_sha256
    if uploaded:
        version = await NativeTemplateVersionService.upload_native_docx_version(
            session,
            tenant_scope=scope,
            legal_entity_id=legal_entity_id,
            template_id=int(template.id),
            filename=spec.source_filename,
            content=source.content,
            placeholder_contract=source.contract,
            storage=storage,
            change_note=f"Пакет {bundle.bundle_id}",
        )
        version = await NativeTemplateVersionService.activate_version(
            session,
            tenant_scope=scope,
            legal_entity_id=legal_entity_id,
            template_id=int(template.id),
            version_id=int(version.id),
        )
        version_id = version.id
    return {
        "key": spec.key,
        "template_id": template.id,
        "created": created,
        "metadata_updated": changed,
        "version_uploaded": uploaded,
        "activated_version_id": version_id,
    }


async def _run(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    source_dir = Path(args.source_dir).expanduser().resolve()
    bundle = load_bundle(manifest_path)
    prepared = prepare_sources(bundle, source_dir)
    async with _bundle_apply_lock(
        tenant_id=args.tenant_id,
        legal_entity_id=args.legal_entity_id,
        enabled=args.command == "apply",
    ):
        async with async_session_maker() as session:
            scope, plan = await inspect_bundle(
                session,
                tenant_id=args.tenant_id,
                legal_entity_id=args.legal_entity_id,
                bundle=bundle,
            )
            report: dict[str, Any] = {
                "bundle_id": bundle.bundle_id,
                "mode": args.command,
                "tenant_id": args.tenant_id,
                "legal_entity_id": args.legal_entity_id,
                "source_count": len(prepared),
                "plan": plan,
            }
            if args.command == "apply":
                if args.confirm_bundle_id != bundle.bundle_id:
                    raise BundleError(
                        "Для применения передайте --confirm-bundle-id с точным bundle_id"
                    )
                report["results"] = await apply_bundle(
                    session,
                    scope=scope,
                    legal_entity_id=args.legal_entity_id,
                    bundle=bundle,
                    prepared=prepared,
                )
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


@asynccontextmanager
async def _bundle_apply_lock(
    *,
    tenant_id: int,
    legal_entity_id: int,
    enabled: bool,
) -> AsyncIterator[None]:
    if not enabled or engine.dialect.name != "postgresql":
        yield
        return
    identity = f"native-template-bundle:{tenant_id}:{legal_entity_id}"
    lock_key = int.from_bytes(
        sha256(identity.encode("utf-8")).digest()[:8],
        byteorder="big",
        signed=True,
    )
    async with engine.connect() as connection:
        acquired = await connection.scalar(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": lock_key},
        )
        if not acquired:
            raise BundleError("Этот пакет уже применяется другим процессом")
        try:
            yield
        finally:
            await connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": lock_key},
            )


async def _tenant_scope(session: AsyncSession, *, tenant_id: int) -> TenantScope:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or tenant.status != "active":
        raise BundleError("Активный tenant не найден")
    storefront = (
        await session.execute(
            select(Storefront)
            .where(Storefront.tenant_id == tenant_id)
            .order_by(Storefront.is_default.desc(), Storefront.id)
        )
    ).scalars().first()
    if storefront is None:
        raise BundleError("Storefront для tenant не найден")
    return TenantScope(
        tenant_id=tenant_id,
        storefront_id=int(storefront.id),
        is_system=bool(tenant.is_system),
        is_canonical_storefront=bool(storefront.is_default),
    )


async def _matching_template(
    session: AsyncSession,
    *,
    tenant_id: int,
    legal_entity_id: int,
    spec: TemplateSpec,
) -> DocumentTemplate | None:
    names = {spec.name, *spec.aliases}
    rows = list(
        (
            await session.execute(
                select(DocumentTemplate).where(
                    DocumentTemplate.tenant_id == tenant_id,
                    DocumentTemplate.legal_entity_id == legal_entity_id,
                    DocumentTemplate.doc_type == spec.doc_type,
                    DocumentTemplate.name.in_(names),
                )
            )
        ).scalars().all()
    )
    if len(rows) > 1:
        raise BundleError(
            f"Для {spec.key} найдено несколько карточек шаблона: "
            + ", ".join(str(item.id) for item in rows)
        )
    return rows[0] if rows else None


def _metadata_changes(
    template: DocumentTemplate | None,
    spec: TemplateSpec,
) -> list[str]:
    if template is None:
        return []
    expected = {
        "name": spec.name,
        "description": spec.description,
        "contract_scenario": spec.contract_scenario,
        "business_role": spec.business_role,
        "sort_order": spec.sort_order,
        "is_active": True,
    }
    return [key for key, value in expected.items() if getattr(template, key) != value]


def _apply_metadata(template: DocumentTemplate, spec: TemplateSpec) -> bool:
    changes = _metadata_changes(template, spec)
    for key in changes:
        value = {
            "name": spec.name,
            "description": spec.description,
            "contract_scenario": spec.contract_scenario,
            "business_role": spec.business_role,
            "sort_order": spec.sort_order,
            "is_active": True,
        }[key]
        setattr(template, key, value)
    return bool(changes)


def _discover_contract(content: bytes) -> NativeTemplatePlaceholderContract:
    renderer = NativeDocxRenderer()
    discovered = renderer.discover_placeholders(content)
    discovered_conditions = renderer.discover_conditions(content)
    tables: list[TableBlockSpec] = []
    for name, fields in (
        ("lines", LINE_ROW_PLACEHOLDERS),
        ("payment_schedule", PAYMENT_SCHEDULE_ROW_PLACEHOLDERS),
    ):
        if name in discovered or any(item.name in discovered for item in fields):
            tables.append(
                TableBlockSpec(name=name, row_fields=frozenset(item.name for item in fields))
            )
    return NativeTemplatePlaceholderContract.create(
        field_catalog=(
            item.name for item in SCALAR_PLACEHOLDERS if item.name in discovered
        ),
        condition_catalog=(
            item.name
            for item in CONDITIONAL_FLAGS
            if item.name in discovered_conditions
        ),
        table_blocks=tables,
    )


def _template_spec(value: object) -> TemplateSpec:
    if not isinstance(value, dict):
        raise BundleError("Каждый шаблон должен быть JSON-объектом")
    doc_type = _required_text(value.get("doc_type"), "doc_type", 64).lower()
    if doc_type not in SUPPORTED_NATIVE_DOCUMENT_TYPES:
        raise BundleError(f"Неподдерживаемый тип документа: {doc_type}")
    source_filename = _required_text(
        value.get("source_filename"), "source_filename", 255
    )
    if PurePath(source_filename).name != source_filename or not source_filename.lower().endswith(".docx"):
        raise BundleError("source_filename должен быть безопасным именем DOCX")
    checksum = _required_text(value.get("sha256"), "sha256", 64).lower()
    if not _SHA256.fullmatch(checksum):
        raise BundleError("sha256 должен быть 64-символьным hex-значением")
    raw_aliases = value.get("aliases", [])
    if not isinstance(raw_aliases, list):
        raise BundleError("aliases должен быть списком")
    aliases = tuple(_required_text(item, "alias", 200) for item in raw_aliases)
    scenario = _optional_text(value.get("contract_scenario"), 64)
    role = _optional_text(value.get("business_role"), 64)
    if scenario is not None and (doc_type != "contract" or scenario not in _CONTRACT_SCENARIOS):
        raise BundleError("Некорректный contract_scenario в манифесте")
    if role is not None and (doc_type != "invoice" or role not in _BUSINESS_ROLES):
        raise BundleError("Некорректный business_role в манифесте")
    try:
        sort_order = int(value.get("sort_order", 0))
    except (TypeError, ValueError) as exc:
        raise BundleError("sort_order должен быть целым числом") from exc
    if not 0 <= sort_order <= 10_000:
        raise BundleError("sort_order должен быть от 0 до 10000")
    return TemplateSpec(
        key=_required_text(value.get("key"), "key", 120),
        name=_required_text(value.get("name"), "name", 200),
        aliases=aliases,
        doc_type=doc_type,
        source_filename=source_filename,
        checksum_sha256=checksum,
        description=_optional_text(value.get("description"), 1000),
        sort_order=sort_order,
        contract_scenario=scenario,
        business_role=role,
    )


def _required_text(value: object, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise BundleError(f"Поле {label} обязательно и не длиннее {maximum} символов")
    return normalized


def _optional_text(value: object, maximum: int) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise BundleError(f"Значение не должно быть длиннее {maximum} символов")
    return normalized


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--legal-entity-id", type=int, required=True)
    parser.add_argument("--confirm-bundle-id")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.tenant_id <= 0 or args.legal_entity_id <= 0:
        raise SystemExit("tenant-id и legal-entity-id должны быть положительными")
    try:
        return asyncio.run(_run(args))
    except BundleError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
