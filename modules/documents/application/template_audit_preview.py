"""Render an inactive proposal against explicit fictional values, without CRM writes."""

import asyncio

from fastapi import HTTPException
from sqlalchemy import select

from models import DocumentTemplateAuditProposal
from api_contracts.document_template_audits import TemplateAuditPreviewContext
from modules.documents.application.template_audit import TemplateAuditService
from modules.documents.application.template_audit_commands import TemplateAuditCommands
from modules.documents.application.native_template_discovery import (
    resolve_native_placeholder_contract,
)
from modules.documents.infrastructure.renderers import NativeDocxRenderer, RenderContext
from modules.documents.infrastructure.renderers.contracts import (
    DocumentTemplateVersion as RenderTemplate,
)


async def proposal_material(session, actor, report_id, proposal_id, *, storage=None):
    row = await TemplateAuditCommands.report(session, actor, report_id)
    issuer, template, customer, links, versions = await TemplateAuditService.scope(
        session, actor, row.legal_entity_id, row.template_id, row.customer_id
    )
    _, current_hash = TemplateAuditService.context(
        issuer, template, customer, links, versions
    )
    proposal = (
        await session.execute(
            select(DocumentTemplateAuditProposal).where(
                DocumentTemplateAuditProposal.id == proposal_id,
                DocumentTemplateAuditProposal.report_id == row.id,
                DocumentTemplateAuditProposal.tenant_id == actor.tenant_scope.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise HTTPException(404, "Template proposal not found")
    version = next((v for v in versions if v.id == proposal.version_id), None)
    if version is None or version.checksum_sha256 != proposal.source_hash:
        raise HTTPException(409, "Proposal source changed")
    if (
        current_hash != proposal.context_hash
        or row.context_hash != current_hash
        or row.legal_sources_hash != proposal.legal_sources_hash
    ):
        raise HTTPException(
            409, "Proposal context/legal evidence changed; review again"
        )
    source, parsed = await TemplateAuditService.material(
        actor, template, version, storage=storage
    )
    if source is None or not parsed["coverage"]["complete"]:
        raise HTTPException(409, "Proposal source unavailable or incomplete")
    contract = await asyncio.to_thread(
        resolve_native_placeholder_contract, source, version.placeholder_schema
    )
    return row, template, proposal, version, source, contract


async def fictional_preview_context(
    session, actor, report_id, proposal_id, *, storage=None
):
    row, template, proposal, version, source, contract = await proposal_material(
        session, actor, report_id, proposal_id, storage=storage
    )
    values = {name: "Тестовое значение" for name in contract.field_catalog}
    for name in values:
        if name.endswith(("name", "full_name", "legal_name", "short_name")):
            values[name] = "Вымышленная сторона для проверки"
        elif any(
            key in name for key in ("price", "amount", "total", "cost", "quantity")
        ):
            values[name] = "100.00"
        elif "date" in name:
            values[name] = "10.11.2026"
    values.update(
        {
            k: v
            for k, v in {
                "seller.name": "ООО Тестовый исполнитель",
                "customer.name": "Иван Тестовый",
                "totals.vat_label": "ТЕСТ: без НДС",
                "document.official_number": "ТЕСТ-001",
            }.items()
            if k in values
        }
    )
    conditions = {name: False for name in contract.condition_catalog}
    for flag in (
        "customer.is_individual",
        "customer.signs_self",
        "customer.individual_self",
        "seller.is_organization",
        "seller.signs_as_statutory_body",
        "seller.organization_statutory_body",
        "seller.is_not_vat_payer",
    ):
        if flag in conditions:
            conditions[flag] = True
    rows = {
        block.name: [{field: "Тестовая строка" for field in block.row_fields}]
        for block in contract.table_blocks
    }
    from modules.documents.domain import (
        SCALAR_PLACEHOLDERS,
        CONDITIONAL_FLAGS,
        LINE_ROW_PLACEHOLDERS,
        PAYMENT_SCHEDULE_ROW_PLACEHOLDERS,
    )
    from modules.documents.domain.placeholder_catalog import (
        MAINTENANCE_OBSERVATION_ROW_PLACEHOLDERS,
    )

    field_labels = {item.name: item.label for item in SCALAR_PLACEHOLDERS}
    condition_labels = {item.name: item.label for item in CONDITIONAL_FLAGS}
    row_labels = {
        item.name: item.label
        for item in (
            *LINE_ROW_PLACEHOLDERS,
            *PAYMENT_SCHEDULE_ROW_PLACEHOLDERS,
            *MAINTENANCE_OBSERVATION_ROW_PLACEHOLDERS,
        )
    }
    return TemplateAuditPreviewContext(
        synthetic=True,
        label="Физлицо, без НДС — вымышленные данные",
        values=values,
        conditions=conditions,
        table_rows=rows,
        source_hash=proposal.source_hash,
        context_hash=row.context_hash,
        legal_sources_hash=row.legal_sources_hash,
        field_labels={key: field_labels.get(key, "Поле документа") for key in values},
        condition_labels={
            key: condition_labels.get(key, "Условие документа") for key in conditions
        },
        table_labels={
            key: {
                "lines": "Товары и работы",
                "payment_schedule": "График оплаты",
                "observations": "Замечания",
            }.get(key, "Строки документа")
            for key in rows
        },
        row_field_labels={
            key: row_labels.get(key, "Значение строки")
            for block in contract.table_blocks
            for key in block.row_fields
        },
    )


async def render_proposal_preview(
    session, actor, report_id, proposal_id, inputs, *, pdf_converter, storage=None
):
    row, template, proposal, version, source, contract = await proposal_material(
        session, actor, report_id, proposal_id, storage=storage
    )
    if (
        inputs.source_hash != proposal.source_hash
        or inputs.context_hash != proposal.context_hash
        or inputs.legal_sources_hash != proposal.legal_sources_hash
    ):
        raise HTTPException(409, "Preview source/context/evidence changed")
    if set(inputs.values) != set(contract.field_catalog) or set(
        inputs.conditions
    ) != set(contract.condition_catalog):
        raise HTTPException(
            400,
            "Select every field and conditional branch explicitly for the fictional preview",
        )
    if set(inputs.table_rows) != {block.name for block in contract.table_blocks}:
        raise HTTPException(400, "Supply every declared table in the fictional preview")
    for block in contract.table_blocks:
        if any(
            set(row) != set(block.row_fields) for row in inputs.table_rows[block.name]
        ):
            raise HTTPException(
                400, "Preview table fields do not match the native contract"
            )
    if (
        sum(len(v) for v in inputs.values.values())
        + sum(len(str(r)) for rows in inputs.table_rows.values() for r in rows)
        > 200000
    ):
        raise HTTPException(400, "Fictional preview context is too large")
    render = RenderTemplate(
        template_key=f"template-{template.id}",
        version=version.version,
        source=source,
        field_catalog=contract.field_catalog,
        condition_catalog=contract.condition_catalog,
        table_blocks=contract.table_blocks,
        filename=version.source_filename or "template.docx",
    )
    context = RenderContext(
        values=inputs.values,
        conditions=inputs.conditions,
        table_rows=inputs.table_rows,
        document_role_type=template.document_role_type,
    )
    docx = await asyncio.to_thread(
        lambda: NativeDocxRenderer().render(render, context).content
    )
    if inputs.format == "docx":
        return docx
    return await asyncio.to_thread(
        pdf_converter.convert_docx, docx, filename="template-audit-preview.docx"
    )


async def assert_audit_proposal_activation(session, *, tenant_scope, template, target):
    """Existing activation remains the sole explicit Manager lifecycle command."""
    proposal = (
        await session.execute(
            select(DocumentTemplateAuditProposal)
            .where(
                DocumentTemplateAuditProposal.version_id == target.id,
                DocumentTemplateAuditProposal.tenant_id == tenant_scope.tenant_id,
            )
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if proposal is None:
        return
    from models import (
        DocumentTemplateAudit,
        DocumentLegalEntity,
        DocumentTemplateCustomerLink,
        DocumentTemplateVersion,
    )
    from services.tenant_entity_access_service import TenantEntityAccessService

    report = await session.get(
        DocumentTemplateAudit,
        proposal.report_id,
        populate_existing=True,
        with_for_update=True,
    )
    issuer = await session.get(
        DocumentLegalEntity,
        template.legal_entity_id,
        populate_existing=True,
        with_for_update=True,
    )
    customer = (
        await TenantEntityAccessService.get_customer(
            session, report.customer_id, tenant_scope=tenant_scope
        )
        if report.customer_id
        else None
    )
    if customer is not None:
        await session.refresh(customer, with_for_update=True)
    links = (
        (
            await session.execute(
                select(DocumentTemplateCustomerLink.customer_id).where(
                    DocumentTemplateCustomerLink.template_id == template.id
                )
            )
        )
        .scalars()
        .all()
    )
    versions = (
        (
            await session.execute(
                select(DocumentTemplateVersion)
                .where(DocumentTemplateVersion.template_id == template.id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    _, current_hash = TemplateAuditService.context(
        issuer, template, customer, links, versions
    )
    if (
        issuer.status != "active"
        or not template.is_active
        or current_hash != proposal.context_hash
        or report.legal_sources_hash != proposal.legal_sources_hash
        or target.checksum_sha256 != proposal.source_hash
        or not any(
            v.id == report.version_id and v.checksum_sha256 == report.source_hash
            for v in versions
        )
        or (
            template.client_restricted
            and (customer is None or customer.id not in links)
        )
    ):
        raise HTTPException(
            409,
            "Audit proposal source/context/evidence changed; review before activation",
        )
