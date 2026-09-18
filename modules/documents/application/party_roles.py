"""Resolve and freeze native party labels, with historical-contract compatibility."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession
from models import (
    CustomerContract,
    DocumentTemplate,
    DocumentTemplateVersion,
    Order,
    OrderDocument,
)
from modules.documents.domain.roles import DEFAULT_DOCUMENT_ROLE_TYPE, ROLE_FORMS
from modules.documents.infrastructure.renderers.docx_party_roles import (
    detect_template_role_type,
)
from modules.documents.infrastructure.template_source_storage import TemplateSourceStorage

if TYPE_CHECKING:
    from .context_builder import DocumentContextSelection


def _role(value: Any) -> str | None:
    value = getattr(value, "value", value)
    return value if value in ROLE_FORMS else None


def snapshot_role(snapshot: dict[str, Any] | None) -> str | None:
    snapshot = snapshot or {}
    return _role((snapshot.get("meta") or {}).get("document_role_type")) or _role(
        (snapshot.get("values") or {}).get("document.role_type")
    )


async def _source_role(
    version: DocumentTemplateVersion | None,
    storage: TemplateSourceStorage | None,
    tenant_id: int,
) -> str | None:
    if version is None or storage is None:
        return None
    source = await storage.read_persisted(
        tenant_id=tenant_id,
        template_id=version.template_id,
        version=version.version,
        storage_key=version.source_storage_key,
        filename=version.source_filename or "template.docx",
        checksum_sha256=version.checksum_sha256,
    )
    return await asyncio.to_thread(detect_template_role_type, source)


async def resolve_party_roles(
    session: AsyncSession,
    *,
    selection: DocumentContextSelection,
    order: Order,
    base_document: OrderDocument | None,
    base_contract: CustomerContract | None,
    template: DocumentTemplate | None = None,
    version: DocumentTemplateVersion | None = None,
    template_storage: TemplateSourceStorage | None = None,
) -> tuple[str, str]:
    """An explicit choice wins; related documents inherit the selected basis."""
    if selection.document_role_type is not None:
        role = _role(selection.document_role_type)
        if role is None:
            raise ValueError("Некорректный тип ролей сторон")
        return role, "explicit"
    if base_document is not None:
        frozen = snapshot_role(base_document.render_snapshot)
        if frozen:
            return frozen, "basis"
        old_template = (
            await session.get(DocumentTemplate, base_document.document_template_id)
            if base_document.document_template_id else None
        )
        # Before role snapshots existed, inspect the exact immutable template
        # revision of the basis, not today's active template or order settings.
        old_version = (
            await session.get(DocumentTemplateVersion, base_document.template_version_id)
            if base_document.template_version_id else None
        )
        if old_version is not None:
            if (
                old_template is None
                or old_template.tenant_id != order.tenant_id
                or old_version.template_id != base_document.document_template_id
            ):
                raise ValueError("Версия шаблона договора не принадлежит заказу")
            detected = await _source_role(old_version, template_storage, order.tenant_id)
            if detected:
                return detected, "basis_template"
        if old_template is not None and old_template.tenant_id == order.tenant_id:
            role = _role(old_template.document_role_type)
            if role:
                return role, "basis_template"
        scenario = ((base_document.render_snapshot or {}).get("values") or {}).get(
            "contract.scenario"
        )
        if scenario:
            role = (
                "executor_customer"
                if scenario in {"services", "repair", "maintenance", "installation"}
                else DEFAULT_DOCUMENT_ROLE_TYPE
            )
            return role, "basis_scenario"
        return _role(order.document_role_type) or DEFAULT_DOCUMENT_ROLE_TYPE, "basis_default"
    if base_contract is not None:
        return _role(base_contract.document_role_type) or DEFAULT_DOCUMENT_ROLE_TYPE, "basis"
    order_role = _role(order.document_role_type)
    if order_role:
        return order_role, "order"
    if (
        selection.document_type != "contract"
        and getattr(order.customer_contract, "status", None) == "active"
    ):
        contract_role = _role(order.customer_contract.document_role_type)
        if contract_role:
            return contract_role, "contract"
    template_role = _role(getattr(template, "document_role_type", None))
    if template_role:
        return template_role, "template"
    detected = await _source_role(version, template_storage, order.tenant_id)
    if detected:
        return detected, "template"
    scenario = getattr(selection.business_terms, "contract_scenario", None)
    if scenario in {"services", "repair", "maintenance", "installation"}:
        return "executor_customer", "scenario"
    return DEFAULT_DOCUMENT_ROLE_TYPE, "default"
