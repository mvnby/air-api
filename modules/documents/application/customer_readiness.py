"""Selected-template customer requirements, based only on frozen factual values."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import re

from modules.documents.domain.party import INDIVIDUAL, INDIVIDUAL_ENTREPRENEUR, SELF
from modules.documents.domain.placeholder_catalog import SCALAR_PLACEHOLDERS
from modules.documents.infrastructure.renderers import NativeDocxRenderer
from .context_builder import DocumentContextBuilder
from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from .template_selection import (
    resolve_template_use_case,
    select_active_native_template,
    load_document_template_version,
)


READINESS_DOCUMENT_TYPES = frozenset({"contract", "invoice", "act", "repair_defect_act", "retail_receipt", "warranty_certificate"})
CHECKED_CUSTOMER_FIELDS = frozenset(
    {
        "customer.display_name",
        "customer.full_name",
        "customer.unp",
        "customer.legal_address",
        "customer.bank_name",
        "customer.iban",
        "customer.bic",
        "customer.signer_position",
        "customer.signer_name",
        "customer.acting_basis",
        "customer.phone",
        "customer.email",
        "customer.city",
    }
)
LABELS = {item.name: item.label for item in SCALAR_PLACEHOLDERS}


def _present(value) -> bool:
    text = str(value or "").strip()
    return bool(text) and not re.fullmatch(r"[\s_.‐‑‒–—―−-]+(?:\s*\([^()]*\))?", text)


def snapshot_customer_readiness(
    snapshot: dict, *, source: bytes, document_type: str
) -> dict:
    if document_type not in READINESS_DOCUMENT_TYPES:
        return {"checked": False, "missing_fields": [], "can_issue": True}
    if not isinstance(snapshot, Mapping) or not isinstance(
        snapshot.get("values"), Mapping
    ):
        raise ValueError(
            "Сохранённый снимок документа повреждён: отсутствует каталог фактических значений"
        )
    values = snapshot["values"]
    for field in CHECKED_CUSTOMER_FIELDS:
        if values.get(field) is not None and not isinstance(values[field], str):
            raise ValueError(
                "Сохранённый снимок документа повреждён: поле клиента должно быть строкой: "
                + LABELS[field]
            )
    if not isinstance(snapshot.get("conditions", {}), Mapping):
        raise ValueError(
            "Сохранённый снимок документа повреждён: каталог условий должен быть объектом"
        )
    entity = values.get("customer.entity_type")
    mode = values.get("customer.signing_mode")
    effective = NativeDocxRenderer().discover_active_placeholders(
        source, snapshot.get("conditions") or {}
    )
    applicable = set(CHECKED_CUSTOMER_FIELDS)
    if entity == INDIVIDUAL:
        applicable -= {
            "customer.unp",
            "customer.bank_name",
            "customer.iban",
            "customer.bic",
        }
    if entity in {INDIVIDUAL, INDIVIDUAL_ENTREPRENEUR}:
        applicable.discard("customer.signer_position")
    if mode == SELF:
        applicable -= {
            "customer.signer_position",
            "customer.signer_name",
            "customer.acting_basis",
        }
    missing = [
        {
            "field": field,
            "label": (
                "Адрес клиента"
                if entity == INDIVIDUAL and field == "customer.legal_address"
                else "ФИО клиента"
                if entity == INDIVIDUAL
                and field in {"customer.full_name", "customer.display_name"}
                else LABELS[field]
            ),
            "critical": False,
        }
        for field in sorted(effective & applicable)
        if not _present(values.get(field))
    ]
    return {
        "checked": True,
        "missing_fields": missing,
        "can_issue": True,
    }


async def source_customer_readiness(
    snapshot, *, template, version, template_storage, document_type
):
    if document_type not in READINESS_DOCUMENT_TYPES:
        return {"checked": False, "missing_fields": [], "can_issue": True}
    if template_storage is None:
        raise ManagedDocumentConflictError(
            "Для проверки реквизитов требуется исходный DOCX шаблона"
        )
    source = await template_storage.read_persisted(
        tenant_id=template.tenant_id,
        template_id=template.id,
        version=version.version,
        storage_key=version.source_storage_key,
        filename=str(version.source_filename or "template.docx"),
        checksum_sha256=version.checksum_sha256,
    )
    return await asyncio.to_thread(
        snapshot_customer_readiness,
        snapshot,
        source=source,
        document_type=document_type,
    )


async def check_selection_readiness(
    session, *, tenant_scope, selection, template_id, template_storage
):
    from .lifecycle_service import ManagedDocumentService

    order = await ManagedDocumentService._get_mutable_scoped_order(
        session,
        tenant_scope=tenant_scope,
        order_id=selection.order_id,
        require_mutable=True,
    )
    if order is None:
        raise ManagedDocumentNotFoundError("Заказ не найден")
    scenario, role = resolve_template_use_case(selection)
    try:
        template, version = await select_active_native_template(
            session,
            tenant_scope=tenant_scope,
            legal_entity_id=selection.legal_entity_id,
            document_type=selection.document_type,
            template_id=template_id,
            contract_scenario=scenario,
            business_role=role,
        )
    except ManagedDocumentNotFoundError:
        if selection.document_type not in {"repair_defect_act", "retail_receipt", "warranty_certificate"} or template_id is not None:
            raise
        from .initial_templates import check_initial_template_available
        if selection.document_type == "repair_defect_act":
            from modules.documents.infrastructure.renderers.repair_defect_template import template_bytes
        else:
            from functools import partial
            from modules.documents.infrastructure.renderers.sale_templates import template_bytes as sale_template_bytes
            template_bytes = partial(sale_template_bytes, selection.document_type)

        await check_initial_template_available(
            session, scope=tenant_scope, legal_entity_id=selection.legal_entity_id,
            document_type=selection.document_type,
        )
        snapshot = await DocumentContextBuilder.build(session, tenant_scope=tenant_scope, selection=selection)
        # First-use preflight reads the built-in form without installing or persisting a version.
        readiness = await asyncio.to_thread(
            lambda: snapshot_customer_readiness(snapshot, source=template_bytes(), document_type=selection.document_type)
        )
        return {**readiness, "template_id": None, "template_version_id": None}
    snapshot = await DocumentContextBuilder.build(
        session,
        tenant_scope=tenant_scope,
        selection=selection,
        template=template,
        template_version=version,
        template_storage=template_storage,
    )
    readiness = await source_customer_readiness(
        snapshot,
        template=template,
        version=version,
        template_storage=template_storage,
        document_type=selection.document_type,
    )
    return {**readiness, "template_id": template.id, "template_version_id": version.id}


async def check_saved_document_readiness(
    session, *, tenant_scope, document, template_storage
):
    if document.doc_type not in READINESS_DOCUMENT_TYPES or document.status != "draft":
        return {"checked": False, "missing_fields": [], "can_issue": True}
    template, version = await load_document_template_version(
        session, tenant_scope=tenant_scope, document=document
    )
    return await source_customer_readiness(
        document.render_snapshot or {},
        template=template,
        version=version,
        template_storage=template_storage,
        document_type=document.doc_type,
    )
