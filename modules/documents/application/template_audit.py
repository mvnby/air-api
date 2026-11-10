"""Read-only source and applicability projection shared by MCP and Manager."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from core.config import settings
from models import (
    DocumentLegalEntity,
    DocumentTemplateAudit,
    DocumentTemplate,
    DocumentTemplateCustomerLink,
    DocumentTemplateVersion,
)
from api_contracts.document_template_audits import (
    TemplateAuditListResult,
    TemplateAuditReadResult,
)
from modules.documents.application.template_versions import NativeTemplateVersionService
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)
from services.manager_tenant_access_service import (
    ManagerTenantAccessResolver,
    ManagerTenantAccessResolutionError,
)
from services.private_attachment_storage_service import get_private_attachment_storage
from services.tenant_entity_access_service import TenantEntityAccessService


CHECKLIST = frozenset(
    {
        "tax_and_price",
        "subject_and_roles",
        "payment",
        "acceptance",
        "warranty",
        "liability",
        "scope_changes",
        "contract_act_annexes",
    }
)


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def manager_url(issuer_id, *, report_id=None, template_id=None):
    query = {"legalEntityId": issuer_id}
    if report_id:
        query["auditReportId"] = report_id
    if template_id:
        query["templateId"] = template_id
    return (
        f"{settings.MANAGER_BASE_URL.rstrip('/')}/settings/documents?{urlencode(query)}"
    )


def version_item(row):
    return {
        "id": row.id,
        "version": row.version,
        "status": row.status,
        "renderer": row.renderer,
        "source_hash": row.checksum_sha256,
        "source_filename": row.source_filename,
        "created_at": row.created_at.isoformat(),
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
        "change_note": row.change_note,
    }


class TemplateAuditService:
    @staticmethod
    async def authorize(session, actor, *, write=False):
        try:
            access = await ManagerTenantAccessResolver.resolve(
                session,
                staff_user_id=actor.staff_user_id,
                tenant_id=actor.tenant_scope.tenant_id,
            )
        except ManagerTenantAccessResolutionError as exc:
            raise HTTPException(
                403,
                "Active company owner/admin membership required for template audits",
            ) from exc
        if (
            access.role not in {"owner", "admin"}
            or access.tenant_scope.storefront_id != actor.tenant_scope.storefront_id
        ):
            raise HTTPException(
                403, "Template auditing requires company owner/admin access"
            )
        if write and access.tenant_scope.demo_read_only:
            raise HTTPException(403, "Demo access is read-only")

    @classmethod
    async def scope(
        cls, session, actor, issuer_id, template_id, customer_id=None, *, lock=False
    ):
        await cls.authorize(session, actor, write=lock)
        if lock:
            # Await the same template mutex as upload/activation before reading
            # any applicability facts. Recheck authority after a queued wait.
            await NativeTemplateVersionService._lock_template(
                session, actor.tenant_scope.tenant_id, template_id
            )
            await cls.authorize(session, actor, write=True)
        issuer_query = (
            select(DocumentLegalEntity)
            .where(
                DocumentLegalEntity.id == issuer_id,
                DocumentLegalEntity.tenant_id == actor.tenant_scope.tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        template_query = (
            select(DocumentTemplate)
            .where(
                DocumentTemplate.id == template_id,
                DocumentTemplate.tenant_id == actor.tenant_scope.tenant_id,
                DocumentTemplate.legal_entity_id == issuer_id,
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            issuer_query = issuer_query.with_for_update()
            template_query = template_query.with_for_update()
        issuer = (await session.execute(issuer_query)).scalar_one_or_none()
        template = (await session.execute(template_query)).scalar_one_or_none()
        if issuer is None or template is None or issuer.status != "active":
            raise HTTPException(404, "Active company issuer/template not found")
        customer = None
        if customer_id:
            customer = await TenantEntityAccessService.get_customer(
                session, customer_id, tenant_scope=actor.tenant_scope, for_update=lock
            )
            if customer is not None:
                await session.refresh(customer, with_for_update=True if lock else None)
            if (
                customer is None
                or customer.is_archived
                or customer.tenant_id != actor.tenant_scope.tenant_id
            ):
                raise HTTPException(404, "Applicable customer not found")
        links = (
            (
                await session.execute(
                    select(DocumentTemplateCustomerLink.customer_id).where(
                        DocumentTemplateCustomerLink.template_id == template_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if template.client_restricted and (
            customer is None or customer.id not in links
        ):
            raise HTTPException(
                404, "Customer template is unavailable for the selected customer"
            )
        versions = (
            (
                await session.execute(
                    select(DocumentTemplateVersion)
                    .where(DocumentTemplateVersion.template_id == template_id)
                    .order_by(DocumentTemplateVersion.version.desc())
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        return issuer, template, customer, list(links), list(versions)

    @staticmethod
    def context(issuer, template, customer, links, versions):
        from modules.documents.domain import B2C_NATIVE_DOCUMENT_TYPES

        raw_tax = (issuer.requisites or {}).get("tax_profile")
        tax = dict(raw_tax) if isinstance(raw_tax, dict) else {}
        missing = [
            key
            for key in (
                "regime",
                "vat_basis",
                "effective_from",
                "verified_at",
                "official_source",
            )
            if not tax.get(key)
        ]
        result = {
            "issuer": {
                "id": issuer.id,
                "name": issuer.display_name,
                "legal_name": issuer.legal_name,
                "entity_type": issuer.entity_type,
                "unp": issuer.unp,
                "status": issuer.status,
                "declared_is_vat_payer": issuer.is_vat_payer,
                "tax_profile": tax,
                "missing_tax_information": missing,
                "tax_profile_verified": False,
                "tax_note": "CRM facts only. Entity type and the VAT flag do not prove legal tax applicability.",
            },
            "applicability": {
                "scope": "customer" if template.client_restricted else "issuer",
                "customer_id": customer.id if customer else None,
                "customer_type": str(getattr(customer.type, "value", customer.type))
                if customer
                else None,
                "audience": "B2C"
                if template.doc_type in B2C_NATIVE_DOCUMENT_TYPES
                else "unspecified_confirm_per_context",
                "contract_scenario": template.contract_scenario,
                "business_role": template.business_role,
                "document_role_type": template.document_role_type,
                "client_restricted": template.client_restricted,
            },
            "clause_origins": {
                "template": "immutable DOCX source",
                "variables_and_conditions": "server placeholder catalog and frozen document context",
                "tax_label": "issuer declared VAT flag; legal basis must be verified separately",
                "additional_conditions": "explicit document context / tenant condition presets, not silently included in this source",
            },
        }
        # Include all stored issuer/customer profile facts in the guard, including
        # changes not displayed by this compact legal-context projection.
        guard = {
            "context": result,
            "issuer_profile": issuer.model_dump(mode="json"),
            "customer_profile": customer.model_dump(mode="json") if customer else None,
            "template_profile": {
                k: v for k, v in template.model_dump(mode="json").items()
            },
            "customer_links": sorted(links),
            "active_version": next(
                (v.id for v in versions if v.status == "active"), None
            ),
        }
        return result, fingerprint(guard)

    @classmethod
    async def list_templates(cls, session, actor, inputs):
        await cls.authorize(session, actor)
        if (
            inputs.customer_id
            and await TenantEntityAccessService.get_customer(
                session, inputs.customer_id, tenant_scope=actor.tenant_scope
            )
            is None
        ):
            raise HTTPException(404, "Customer not found")
        predicates = [
            DocumentTemplate.tenant_id == actor.tenant_scope.tenant_id,
            DocumentLegalEntity.tenant_id == actor.tenant_scope.tenant_id,
            DocumentLegalEntity.status == "active",
        ]
        if inputs.legal_entity_id:
            issuer = await session.get(DocumentLegalEntity, inputs.legal_entity_id)
            if (
                issuer is None
                or issuer.tenant_id != actor.tenant_scope.tenant_id
                or issuer.status != "active"
            ):
                raise HTTPException(404, "Active issuer not found")
            predicates.append(
                DocumentTemplate.legal_entity_id == inputs.legal_entity_id
            )
        if inputs.document_type:
            predicates.append(DocumentTemplate.doc_type == inputs.document_type)
        if inputs.contract_scenario:
            predicates.append(
                DocumentTemplate.contract_scenario == inputs.contract_scenario
            )
        if inputs.active is not None:
            predicates.append(DocumentTemplate.is_active == inputs.active)
        linked = select(DocumentTemplateCustomerLink.template_id).where(
            DocumentTemplateCustomerLink.customer_id == inputs.customer_id
        )
        predicates.append(
            or_(
                DocumentTemplate.client_restricted.is_(False),
                DocumentTemplate.id.in_(linked),
            )
            if inputs.customer_id
            else DocumentTemplate.client_restricted.is_(False)
        )
        base = (
            select(DocumentTemplate)
            .join(
                DocumentLegalEntity,
                DocumentLegalEntity.id == DocumentTemplate.legal_entity_id,
            )
            .where(*predicates)
        )
        total = (
            await session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    base.order_by(DocumentTemplate.id)
                    .offset((inputs.page - 1) * inputs.limit)
                    .limit(inputs.limit)
                )
            )
            .scalars()
            .all()
        )
        return TemplateAuditListResult(
            items=[
                {
                    "id": t.id,
                    "legal_entity_id": t.legal_entity_id,
                    "name": t.name,
                    "document_type": t.doc_type,
                    "active": t.is_active,
                    "customer_restricted": t.client_restricted,
                    "contract_scenario": t.contract_scenario,
                    "business_role": t.business_role,
                    "updated_at": str(t.updated_at),
                    "manager_url": manager_url(t.legal_entity_id, template_id=t.id),
                }
                for t in rows
            ],
            page=inputs.page,
            limit=inputs.limit,
            total=total,
        )

    @staticmethod
    async def material(actor, template, version, *, storage=None):
        from modules.documents.infrastructure.template_audit_docx import inspect_docx

        if version.renderer != "docx":
            return None, {
                "blocks": [],
                "coverage": {
                    "complete": False,
                    "reasons": [
                        {
                            "code": "unsupported_renderer",
                            "message": "Read the provider source privately in Manager",
                        }
                    ],
                },
            }
        storage = storage or PrivateTemplateSourceStorage(
            get_private_attachment_storage()
        )
        try:
            source = await storage.read_persisted(
                tenant_id=actor.tenant_scope.tenant_id,
                template_id=template.id,
                version=version.version,
                storage_key=version.source_storage_key,
                filename=version.source_filename or "template.docx",
                checksum_sha256=version.checksum_sha256,
            )
            if hashlib.sha256(source).hexdigest() != version.checksum_sha256:
                raise ValueError("Checksum mismatch")
            parsed = await asyncio.to_thread(inspect_docx, source)
            return source, parsed
        except (OSError, ValueError, RuntimeError):
            return None, {
                "blocks": [],
                "coverage": {
                    "complete": False,
                    "reasons": [
                        {
                            "code": "source_unavailable_or_invalid",
                            "message": "Private source unavailable, invalid or failed integrity verification",
                        }
                    ],
                },
            }

    @classmethod
    async def read(cls, session, actor, inputs, *, storage=None):
        issuer, template, customer, links, versions = await cls.scope(
            session,
            actor,
            inputs.legal_entity_id,
            inputs.template_id,
            inputs.customer_id,
        )
        version = (
            next((v for v in versions if v.id == inputs.version_id), None)
            if inputs.version_id
            else next((v for v in versions if v.status == "active"), None)
        )
        if inputs.version_id and version is None:
            raise HTTPException(404, "Template version not found")
        if version and version.status == "retired" and not inputs.include_archived:
            raise HTTPException(409, "Request archived versions explicitly")
        context, context_hash = cls.context(issuer, template, customer, links, versions)
        source, parsed = (
            await cls.material(actor, template, version, storage=storage)
            if version
            else (
                None,
                {
                    "blocks": [],
                    "coverage": {
                        "complete": False,
                        "reasons": [{"code": "no_active_version"}],
                    },
                },
            )
        )
        source_hash = version.checksum_sha256 if version and source else None
        chunks = []
        for block in parsed["blocks"]:
            text = block["original_text"]
            for offset in range(0, max(1, len(text)), 4000):
                chunks.append(
                    {
                        **{k: v for k, v in block.items() if k != "original_text"},
                        "text": text[offset : offset + 4000],
                        "text_offset": offset,
                        "text_length": len(text),
                        "last_fragment": offset + 4000 >= len(text),
                    }
                )
        position = 0
        binding = [
            inputs.template_id,
            version.id if version else None,
            source_hash,
            context_hash,
        ]
        if inputs.cursor:
            try:
                cursor = json.loads(base64.urlsafe_b64decode(inputs.cursor.encode()))
                if (
                    cursor["binding"] != binding
                    or type(cursor["offset"]) is not int
                    or cursor["offset"] < 0
                ):
                    raise ValueError("Stale cursor")
                position = cursor["offset"]
            except (ValueError, KeyError, TypeError):
                raise HTTPException(
                    409,
                    "Source/context changed or invalid continuation; restart reading",
                ) from None
        end = position + inputs.limit
        next_cursor = (
            base64.urlsafe_b64encode(
                json.dumps({"binding": binding, "offset": end}).encode()
            ).decode()
            if end < len(chunks)
            else None
        )
        visible_versions = [
            v for v in versions if inputs.include_archived or v.status != "retired"
        ]
        from modules.documents.domain import SCALAR_PLACEHOLDERS, CONDITIONAL_FLAGS

        variables = sorted(
            {name for block in parsed["blocks"] for name in block.get("variables", [])}
        )
        flags = sorted(
            {name for block in parsed["blocks"] for name in block.get("conditions", [])}
        )
        catalog = {
            "stored_schema": version.placeholder_schema if version else {},
            "fields": [
                {
                    "name": name,
                    "label": next(
                        (
                            item.label
                            for item in SCALAR_PLACEHOLDERS
                            if item.name == name
                        ),
                        "Unregistered variable",
                    ),
                }
                for name in variables
            ],
            "conditions": [
                {
                    "name": name,
                    "label": next(
                        (item.label for item in CONDITIONAL_FLAGS if item.name == name),
                        "Unregistered condition",
                    ),
                    "rule": "selected explicitly from frozen document context; inspect both true and false branches",
                }
                for name in flags
            ],
            "tables": version.placeholder_schema.get("tables", []) if version else [],
            "selection_rules": context["applicability"],
            "clause_origins": context["clause_origins"],
        }
        audit_where = [
            DocumentTemplateAudit.tenant_id == actor.tenant_scope.tenant_id,
            DocumentTemplateAudit.template_id == template.id,
            DocumentTemplateAudit.customer_id == (customer.id if customer else None),
        ]
        if not inputs.include_archived:
            audit_where.append(
                DocumentTemplateAudit.version_id.in_([v.id for v in visible_versions])
            )
        audit_total = (
            await session.execute(
                select(func.count())
                .select_from(DocumentTemplateAudit)
                .where(*audit_where)
            )
        ).scalar_one()
        audits = (
            (
                await session.execute(
                    select(DocumentTemplateAudit)
                    .where(*audit_where)
                    .order_by(
                        DocumentTemplateAudit.checked_at.desc(),
                        DocumentTemplateAudit.id.desc(),
                    )
                    .offset((inputs.audit_reports_page - 1) * 25)
                    .limit(25)
                )
            )
            .scalars()
            .all()
        )
        audit_summaries = [
            {
                "id": r.id,
                "version_id": r.version_id,
                "version_number": next(
                    (v.version for v in versions if v.id == r.version_id), None
                ),
                "revision": r.revision,
                "checked_at": r.checked_at.isoformat(),
                "open_findings_count": sum(
                    f["status"] not in {"rejected", "fixed"} for f in r.findings
                ),
                "source_hash": r.source_hash,
                "context_hash": r.context_hash,
                "legal_sources_hash": r.legal_sources_hash,
                "stale": r.context_hash != context_hash
                or not any(
                    v.id == r.version_id and v.checksum_sha256 == r.source_hash
                    for v in versions
                ),
                "legal_currency": "requires_external_recheck",
                "manager_url": manager_url(issuer.id, report_id=r.id),
            }
            for r in audits
        ]
        return TemplateAuditReadResult(
            template={
                "id": template.id,
                "name": template.name,
                "document_type": template.doc_type,
                "legal_entity_id": issuer.id,
                "active": template.is_active,
                "updated_at": str(template.updated_at),
            },
            version=version_item(version) if version else None,
            versions=[
                version_item(v)
                for v in visible_versions[
                    (inputs.versions_page - 1) * 25 : inputs.versions_page * 25
                ]
            ],
            versions_total=len(visible_versions),
            audit_reports=audit_summaries,
            audit_reports_total=audit_total,
            audit_reports_next_page=inputs.audit_reports_page + 1
            if inputs.audit_reports_page * 25 < audit_total
            else None,
            context=context,
            context_hash=context_hash,
            source_hash=source_hash,
            coverage=parsed["coverage"],
            blocks=chunks[position:end],
            next_cursor=next_cursor,
            placeholder_catalog=catalog,
            manager_url=manager_url(issuer.id, template_id=template.id),
            source_resource_uri=f"kitlane://template-sources/{issuer.id}/{template.id}/{version.id}"
            + (f"?customer_id={customer.id}" if customer else "")
            if version and source
            else None,
            source_download_url=f"/api/manager/document-system/templates/{template.id}/versions/{version.id}/source?legal_entity_id={issuer.id}"
            if version and source
            else None,
        )


def occurrence_page(blocks, phrase, page=1, limit=100):
    """Bound each context excerpt and paginate matches, even within one block."""
    if not phrase:
        raise ValueError("Occurrence phrase cannot be empty")
    items, total = [], 0
    first, end = (page - 1) * limit, page * limit
    for block in blocks:
        text, offset = block["original_text"], 0
        while (position := text.find(phrase, offset)) >= 0:
            if first <= total < end:
                start = max(0, position - 160)
                excerpt_end = min(len(text), position + min(len(phrase), 500) + 160)
                items.append(
                    {
                        "block_id": block["block_id"],
                        "part": block["part"],
                        "location": block["location"],
                        "text": text[start:excerpt_end],
                        "match_offset": position,
                        "matched_length": len(phrase),
                        "context_start": start,
                        "full_block_length": len(text),
                    }
                )
            total += 1
            offset = position + len(phrase)
    return {
        "occurrences": items,
        "occurrences_total": total,
        "occurrences_page": page,
        "occurrences_next_page": page + 1 if end < total else None,
    }


def decision_is_current(finding, report):
    """Retain a human decision without approving subsequently changed wording."""
    history = finding.get("decision_history", [])
    if not history:
        return None
    last = history[-1]
    return (
        last.get("source_hash") == report.source_hash
        and last.get("context_hash") == report.context_hash
        and last.get("legal_sources_hash") == report.legal_sources_hash
        and "proposed_text" in last
        and last["proposed_text"] == finding.get("proposed_text")
        and last.get("applicability") == finding.get("applicability")
    )
