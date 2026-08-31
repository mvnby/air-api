from __future__ import annotations

from sqlalchemy import case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import DocumentTemplate, DocumentTemplateVersion, OrderDocument
from models.tenancy import TenantScope

from .context_builder import DocumentContextSelection
from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError


def resolve_template_use_case(
    selection: DocumentContextSelection,
) -> tuple[str | None, str | None]:
    document_type = str(selection.document_type).strip().lower()
    scenario = None
    if document_type == "contract" and selection.business_terms is not None:
        scenario = str(selection.business_terms.contract_scenario or "").strip().lower()
        scenario = scenario or None
    role = None
    if document_type == "invoice":
        role = str(selection.business_role or "payment_request").strip().lower()
        if role not in {"payment_request", "offer"}:
            raise ManagedDocumentConflictError("Некорректная роль счёта")
    return scenario, role


async def select_active_native_template(
    session: AsyncSession,
    *,
    tenant_scope: TenantScope,
    legal_entity_id: int,
    document_type: str,
    template_id: int | None,
    contract_scenario: str | None,
    business_role: str | None,
) -> tuple[DocumentTemplate, DocumentTemplateVersion]:
    normalized_type = str(document_type).strip().lower()
    statement = (
        select(DocumentTemplate, DocumentTemplateVersion)
        .join(
            DocumentTemplateVersion,
            DocumentTemplateVersion.template_id == DocumentTemplate.id,
        )
        .where(
            DocumentTemplate.tenant_id == tenant_scope.tenant_id,
            DocumentTemplate.legal_entity_id == legal_entity_id,
            DocumentTemplate.doc_type == normalized_type,
            DocumentTemplate.is_active.is_(True),
            DocumentTemplateVersion.renderer == "docx",
            DocumentTemplateVersion.status == "active",
        )
    )
    use_case_rank = None
    if normalized_type == "contract":
        if contract_scenario is None:
            statement = statement.where(DocumentTemplate.contract_scenario.is_(None))
        else:
            statement = statement.where(
                or_(
                    DocumentTemplate.contract_scenario.is_(None),
                    DocumentTemplate.contract_scenario == contract_scenario,
                )
            )
            use_case_rank = case(
                (DocumentTemplate.contract_scenario == contract_scenario, 0),
                else_=1,
            )
    elif normalized_type == "invoice":
        statement = statement.where(
            or_(
                DocumentTemplate.business_role.is_(None),
                DocumentTemplate.business_role == business_role,
            )
        )
        use_case_rank = case(
            (DocumentTemplate.business_role == business_role, 0),
            else_=1,
        )
    ordering = [] if use_case_rank is None else [use_case_rank]
    statement = statement.order_by(
        *ordering,
        DocumentTemplate.is_default.desc(),
        DocumentTemplate.sort_order,
        DocumentTemplate.id,
    )
    if template_id is not None:
        statement = statement.where(DocumentTemplate.id == template_id)
    row = (await session.execute(statement)).first()
    if row is None:
        raise ManagedDocumentNotFoundError(
            "Для документа нет активной DOCX-версии шаблона"
        )
    return row[0], row[1]


async def load_document_template_version(
    session: AsyncSession,
    *,
    tenant_scope: TenantScope,
    document: OrderDocument,
) -> tuple[DocumentTemplate, DocumentTemplateVersion]:
    row = (
        await session.execute(
            select(DocumentTemplate, DocumentTemplateVersion)
            .join(
                DocumentTemplateVersion,
                DocumentTemplateVersion.template_id == DocumentTemplate.id,
            )
            .where(
                DocumentTemplate.id == document.document_template_id,
                DocumentTemplate.tenant_id == tenant_scope.tenant_id,
                DocumentTemplate.legal_entity_id == document.legal_entity_id,
                DocumentTemplateVersion.id == document.template_version_id,
                DocumentTemplateVersion.renderer == "docx",
            )
        )
    ).first()
    if row is None:
        raise ManagedDocumentNotFoundError(
            "Зафиксированная версия шаблона не найдена"
        )
    return row[0], row[1]
