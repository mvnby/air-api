"""Durable addressed review/proposal commands; never activate or alter documents."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from models import DocumentTemplateAudit, DocumentTemplateAuditProposal
from api_contracts.document_template_audits import TemplateAuditReportResult
from modules.documents.application.native_template_discovery import (
    resolve_native_placeholder_contract,
)
from modules.documents.application.template_audit import (
    CHECKLIST,
    TemplateAuditService,
    fingerprint,
    manager_url,
    occurrence_page,
    decision_is_current,
)
from modules.documents.application.template_versions import NativeTemplateVersionService
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)
from services.authenticated_command_service import AuthenticatedCommandService
from services.private_attachment_storage_service import get_private_attachment_storage
from services.public_write_idempotency_service import PublicWriteCommandResponse


class SavedAudit(BaseModel):
    report_id: int
    proposal_id: int | None = None


def _now():
    return datetime.now(timezone.utc)


def _sources_hash(findings):
    # A recheck timestamp alone does not imply a changed edition. The content
    # digest, exact provision, effective dates and applicability do.
    sources = {
        fingerprint({k: v for k, v in source.items() if k != "checked_at"}): {
            k: v for k, v in source.items() if k != "checked_at"
        }
        for finding in findings
        for source in finding.get("sources", [])
    }
    return fingerprint([sources[key] for key in sorted(sources)])


def _verification(finding, context, review_date):
    if finding["verification"] != "verified":
        return finding["verification"]
    if finding["category"] not in {"tax", "legal_applicability"}:
        return "verified"
    sources = finding["sources"]
    # Evidence is agent-supplied, not server-certified legal advice. Enforce the
    # minimum proof fields and refuse future/unavailable/nonofficial editions.
    if not sources or any(
        not s["official"]
        or s["verification"] != "verified"
        or urlsplit(s["url"]).scheme != "https"
        or s["effective_from"] > str(review_date)
        or (s.get("effective_until") and s["effective_until"] < str(review_date))
        or datetime.fromisoformat(s["checked_at"]).date() != review_date
        or datetime.fromisoformat(s["checked_at"]).tzinfo is None
        or datetime.fromisoformat(s["checked_at"]) > _now()
        for s in sources
    ):
        return "unverified"
    if finding["category"] == "tax" and context["issuer"]["missing_tax_information"]:
        return "unverified"
    return "verified"


class TemplateAuditCommands:
    @staticmethod
    async def report(session, actor, report_id, *, lock=False):
        await TemplateAuditService.authorize(session, actor, write=lock)
        stmt = (
            select(DocumentTemplateAudit)
            .where(
                DocumentTemplateAudit.id == report_id,
                DocumentTemplateAudit.tenant_id == actor.tenant_scope.tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update()
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "Template audit not found")
        return row

    @classmethod
    async def get(
        cls,
        session,
        actor,
        report_id,
        legal_sources_hash=None,
        *,
        occurrences_finding_id=None,
        occurrences_page=1,
        storage=None,
    ):
        row = await cls.report(session, actor, report_id)
        issuer, template, customer, links, versions = await TemplateAuditService.scope(
            session, actor, row.legal_entity_id, row.template_id, row.customer_id
        )
        _, current_hash = TemplateAuditService.context(
            issuer, template, customer, links, versions
        )
        version = next((v for v in versions if v.id == row.version_id), None)
        reasons = []
        if current_hash != row.context_hash:
            reasons.append("issuer_template_or_customer_context_changed")
        if version is None or version.checksum_sha256 != row.source_hash:
            reasons.append("source_version_changed_or_unavailable")
        if legal_sources_hash and legal_sources_hash != row.legal_sources_hash:
            reasons.append("legal_source_evidence_changed")
        proposals = (
            (
                await session.execute(
                    select(DocumentTemplateAuditProposal)
                    .where(
                        DocumentTemplateAuditProposal.report_id == row.id,
                        DocumentTemplateAuditProposal.tenant_id
                        == actor.tenant_scope.tenant_id,
                    )
                    .order_by(DocumentTemplateAuditProposal.id)
                )
            )
            .scalars()
            .all()
        )
        findings = [dict(f) for f in row.findings]
        for finding in findings:
            current = decision_is_current(finding, row)
            finding["decision_current"] = (
                current and not reasons if current is not None else None
            )
        if occurrences_finding_id:
            finding = next(
                (f for f in findings if f["id"] == occurrences_finding_id), None
            )
            if finding is None:
                raise HTTPException(404, "Finding not found")
            if version is None:
                raise HTTPException(409, "Source version unavailable")
            source, parsed = await TemplateAuditService.material(
                actor, template, version, storage=storage
            )
            if source is None:
                raise HTTPException(
                    409, "Private source unavailable for occurrence continuation"
                )
            finding.update(
                await asyncio.to_thread(
                    occurrence_page,
                    parsed["blocks"],
                    finding["original_text"],
                    occurrences_page,
                )
            )
        statuses = {v.id: v.status for v in versions}
        numbers = {v.id: v.version for v in versions}
        checksums = {v.id: v.checksum_sha256 for v in versions}
        return TemplateAuditReportResult(
            id=row.id,
            template_id=row.template_id,
            template_name=template.name,
            version_number=version.version if version else 0,
            version_id=row.version_id,
            legal_entity_id=row.legal_entity_id,
            customer_id=row.customer_id,
            revision=row.revision,
            source_hash=row.source_hash,
            context_hash=row.context_hash,
            legal_sources_hash=row.legal_sources_hash,
            checked_at=row.checked_at,
            coverage=row.coverage,
            checklist=row.checklist,
            findings=findings,
            proposals=[
                {
                    "id": p.id,
                    "base_version_id": p.base_version_id,
                    "version_id": p.version_id,
                    "status": statuses.get(p.version_id, "unavailable"),
                    "version_number": numbers.get(p.version_id),
                    "source_hash": p.source_hash,
                    "edits": p.edits,
                    "created_by": p.created_by,
                    "channel": p.channel,
                    "created_at": p.created_at.isoformat(),
                    "manager_url": manager_url(row.legal_entity_id, report_id=row.id),
                    "stale": p.context_hash != current_hash
                    or p.legal_sources_hash != row.legal_sources_hash
                    or checksums.get(p.version_id) != p.source_hash,
                }
                for p in proposals
            ],
            stale=bool(reasons),
            stale_reasons=reasons,
            legal_currency=(
                "changed"
                if legal_sources_hash and legal_sources_hash != row.legal_sources_hash
                else "matches_supplied_hash"
                if legal_sources_hash
                else "requires_external_recheck"
            ),
            manager_url=manager_url(row.legal_entity_id, report_id=row.id),
        )

    @classmethod
    async def list_reports(
        cls, session, actor, issuer_id, template_id=None, page=1, limit=25
    ):
        await TemplateAuditService.authorize(session, actor)
        from models import DocumentLegalEntity

        issuer = (
            await session.execute(
                select(DocumentLegalEntity)
                .where(
                    DocumentLegalEntity.id == issuer_id,
                    DocumentLegalEntity.tenant_id == actor.tenant_scope.tenant_id,
                    DocumentLegalEntity.status == "active",
                )
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if issuer is None:
            raise HTTPException(404, "Active issuer not found")
        predicates = [
            DocumentTemplateAudit.tenant_id == actor.tenant_scope.tenant_id,
            DocumentTemplateAudit.legal_entity_id == issuer_id,
        ]
        if template_id:
            predicates.append(DocumentTemplateAudit.template_id == template_id)
        total = (
            await session.execute(
                select(func.count())
                .select_from(DocumentTemplateAudit)
                .where(*predicates)
            )
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    select(DocumentTemplateAudit.id)
                    .where(*predicates)
                    .order_by(
                        DocumentTemplateAudit.updated_at.desc(),
                        DocumentTemplateAudit.id.desc(),
                    )
                    .offset((page - 1) * limit)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        # Recheck customer applicability for every result. Revoked access fails
        # closed rather than leaking stored snippets from an old receipt.
        return {
            "items": [await cls.get(session, actor, row) for row in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @staticmethod
    def guard(row, inputs, current_hash):
        if (
            row.revision != inputs.expected_revision
            or row.source_hash != inputs.source_hash
            or row.context_hash != inputs.context_hash
            or current_hash != row.context_hash
            or row.legal_sources_hash != inputs.legal_sources_hash
        ):
            raise HTTPException(
                409, "Review/source/context changed; read the saved report again"
            )

    @classmethod
    async def save(cls, session, actor, inputs, *, storage=None):
        await TemplateAuditService.authorize(session, actor, write=True)
        await TemplateAuditService.scope(
            session,
            actor,
            inputs.legal_entity_id,
            inputs.template_id,
            inputs.customer_id,
        )

        async def operation():
            (
                issuer,
                template,
                customer,
                links,
                versions,
            ) = await TemplateAuditService.scope(
                session,
                actor,
                inputs.legal_entity_id,
                inputs.template_id,
                inputs.customer_id,
                lock=True,
            )
            context, context_hash = TemplateAuditService.context(
                issuer, template, customer, links, versions
            )
            version = next((v for v in versions if v.id == inputs.version_id), None)
            if version is None:
                raise HTTPException(404, "Template version not found")
            if (
                context_hash != inputs.context_hash
                or version.checksum_sha256 != inputs.source_hash
            ):
                raise HTTPException(
                    409, "Template source/context changed; restart review"
                )
            source, parsed = await TemplateAuditService.material(
                actor, template, version, storage=storage
            )
            if source is None:
                raise HTTPException(
                    409,
                    "Private template source unavailable; cannot save a grounded review",
                )
            if (
                inputs.checked_at.tzinfo is None
                or inputs.checked_at > _now()
                or inputs.checked_at.date() != inputs.review_date
            ):
                raise HTTPException(
                    400,
                    "Use an actual timezone-aware check date; future reviews are not accepted",
                )
            if set(inputs.checklist) != CHECKLIST:
                raise HTTPException(
                    400, "Record each item of the template audit checklist explicitly"
                )
            blocks = {b["block_id"]: b for b in parsed["blocks"]}
            findings = []
            for value in inputs.findings:
                item = value.model_dump(mode="json")
                block = blocks.get(item["block_id"])
                if block is None or item["original_text"] not in block["original_text"]:
                    raise HTTPException(
                        409, "Finding does not match the exact source block"
                    )
                part = block["part"]
                section = (
                    "Основной текст"
                    if part.endswith("document.xml")
                    else "Верхний колонтитул"
                    if "header" in part
                    else "Нижний колонтитул"
                    if "footer" in part
                    else "Комментарии"
                    if "comments" in part
                    else "Сноски"
                    if "footnotes" in part
                    else "Концевые примечания"
                    if "endnotes" in part
                    else "Часть документа"
                )
                item["location_label"] = section + (
                    " · таблица" if "/w:tbl" in block["location"] else ""
                )
                item["id"] = fingerprint(
                    [
                        version.id,
                        item["block_id"],
                        item["original_text"],
                        item["category"],
                    ]
                )
                item["verification"] = _verification(item, context, inputs.review_date)
                item["status"] = (
                    "needs_legal_review"
                    if item["verification"] != "verified"
                    else "proposal"
                )
                item["decision_history"] = []
                item.update(
                    await asyncio.to_thread(
                        occurrence_page,
                        parsed["blocks"],
                        item["original_text"],
                    )
                )
                findings.append(item)
            if len({f["id"] for f in findings}) != len(findings):
                raise HTTPException(400, "Duplicate findings in one request")
            sources_hash = _sources_hash(findings)
            if inputs.legal_sources_hash and inputs.legal_sources_hash != sources_hash:
                raise HTTPException(
                    409,
                    "Legal source evidence hash does not match the supplied evidence",
                )
            row = (
                await session.execute(
                    select(DocumentTemplateAudit)
                    .where(
                        DocumentTemplateAudit.tenant_id == actor.tenant_scope.tenant_id,
                        DocumentTemplateAudit.template_id == template.id,
                        DocumentTemplateAudit.version_id == version.id,
                        DocumentTemplateAudit.context_hash == context_hash,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row:
                if row.source_hash != inputs.source_hash:
                    raise HTTPException(
                        409,
                        "Immutable reviewed source changed; use a new template version",
                    )
                old = {f["id"]: f for f in row.findings}
                # Same-version reruns preserve decisions even if proposed wording
                # or evidence is refined. Absence does not delete old findings.
                for item in findings:
                    previous = old.get(item["id"])
                    if previous:
                        item["status"] = previous["status"]
                        item["decision_history"] = previous.get("decision_history", [])
                    old[item["id"]] = item
                merged = list(old.values())
                merged_hash = _sources_hash(merged)
                if inputs.expected_revision != row.revision:
                    if (
                        inputs.expected_revision != 0
                        or merged != row.findings
                        or merged_hash != row.legal_sources_hash
                        or inputs.checklist != row.checklist
                    ):
                        raise HTTPException(
                            409,
                            "Audit revision changed; read the report before updating",
                        )
                else:
                    row.history = [
                        *row.history,
                        {
                            "revision": row.revision,
                            "legal_sources_hash": row.legal_sources_hash,
                            "checked_at": str(row.checked_at),
                        },
                    ]
                    row.findings, row.legal_sources_hash = merged, merged_hash
                    row.coverage, row.checklist = parsed["coverage"], inputs.checklist
                    row.checked_at, row.review_date, row.updated_at = (
                        inputs.checked_at,
                        str(inputs.review_date),
                        _now(),
                    )
                    row.revision += 1
            else:
                if inputs.expected_revision != 0:
                    raise HTTPException(
                        409, "Audit does not exist at the expected revision"
                    )
                row = DocumentTemplateAudit(
                    tenant_id=actor.tenant_scope.tenant_id,
                    legal_entity_id=issuer.id,
                    template_id=template.id,
                    version_id=version.id,
                    customer_id=inputs.customer_id,
                    source_hash=inputs.source_hash,
                    context_hash=context_hash,
                    legal_sources_hash=sources_hash,
                    checked_at=inputs.checked_at,
                    review_date=str(inputs.review_date),
                    coverage=parsed["coverage"],
                    checklist=inputs.checklist,
                    findings=findings,
                    created_by=actor.staff_user_id,
                    channel=actor.channel,
                )
            session.add(row)
            await session.flush()
            return PublicWriteCommandResponse(
                SavedAudit(report_id=row.id),
                resource_type="template_audit",
                resource_id=row.id,
            )

        outcome = await AuthenticatedCommandService.execute(
            session,
            actor=actor,
            command_name="template_audit.save",
            idempotency_key=inputs.idempotency_key,
            payload=inputs.model_dump(mode="json", exclude={"idempotency_key"}),
            response_model=SavedAudit,
            operation=operation,
        )
        return {
            "result": await cls.get(session, actor, outcome.value.report_id),
            "replayed": outcome.replayed,
        }

    @classmethod
    async def propose(cls, session, actor, inputs, *, storage=None):
        await TemplateAuditService.authorize(session, actor, write=True)
        initial = await cls.report(session, actor, inputs.report_id)
        await TemplateAuditService.scope(
            session,
            actor,
            initial.legal_entity_id,
            initial.template_id,
            initial.customer_id,
        )
        storage = storage or PrivateTemplateSourceStorage(
            get_private_attachment_storage()
        )

        async def operation():
            (
                issuer,
                template,
                customer,
                links,
                versions,
            ) = await TemplateAuditService.scope(
                session,
                actor,
                initial.legal_entity_id,
                initial.template_id,
                initial.customer_id,
                lock=True,
            )
            row = await cls.report(session, actor, inputs.report_id, lock=True)
            _, context_hash = TemplateAuditService.context(
                issuer, template, customer, links, versions
            )
            cls.guard(row, inputs, context_hash)
            base = next((v for v in versions if v.id == row.version_id), None)
            if (
                base is None
                or base.checksum_sha256 != row.source_hash
                or not template.is_active
            ):
                raise HTTPException(409, "Source template changed or disabled")
            source, parsed = await TemplateAuditService.material(
                actor, template, base, storage=storage
            )
            if source is None or not parsed["coverage"]["complete"]:
                raise HTTPException(
                    409,
                    "Incomplete source coverage; edit the private source manually in Manager",
                )
            findings = {f["id"]: f for f in row.findings}
            for edit in inputs.edits:
                finding = findings.get(edit.finding_id)
                if (
                    finding is None
                    or finding["block_id"] != edit.block_id
                    or finding["original_text"] not in edit.expected_text
                ):
                    raise HTTPException(
                        409, "Edit must address the linked finding and original block"
                    )
                if finding["status"] in {"rejected", "fixed"}:
                    raise HTTPException(
                        409, "Rejected/fixed finding cannot be silently applied"
                    )
            from modules.documents.infrastructure.template_audit_docx import (
                apply_docx_edits,
                DocxAuditError,
            )

            try:
                content = await asyncio.to_thread(
                    apply_docx_edits,
                    source,
                    [
                        e.model_dump(exclude={"finding_id", "reason"})
                        for e in inputs.edits
                    ],
                )
            except DocxAuditError as exc:
                raise HTTPException(409, str(exc)) from exc
            contract = await asyncio.to_thread(
                resolve_native_placeholder_contract, source, base.placeholder_schema
            )
            version = await NativeTemplateVersionService.upload_native_docx_version(
                session,
                tenant_scope=actor.tenant_scope,
                legal_entity_id=issuer.id,
                template_id=template.id,
                filename=base.source_filename or "template.docx",
                content=content,
                placeholder_contract=contract,
                storage=storage,
                change_note=f"Audit #{row.id}; base version #{base.id}; {actor.channel}",
                commit=False,
            )
            proposal = DocumentTemplateAuditProposal(
                tenant_id=actor.tenant_scope.tenant_id,
                report_id=row.id,
                base_version_id=base.id,
                version_id=version.id,
                source_hash=version.checksum_sha256,
                context_hash=context_hash,
                legal_sources_hash=row.legal_sources_hash,
                edits=[e.model_dump() for e in inputs.edits],
                created_by=actor.staff_user_id,
                channel=actor.channel,
            )
            session.add(proposal)
            row.revision += 1
            row.updated_at = _now()
            session.add(row)
            await session.flush()
            return PublicWriteCommandResponse(
                SavedAudit(report_id=row.id, proposal_id=proposal.id),
                resource_type="template_audit_proposal",
                resource_id=proposal.id,
            )

        outcome = await AuthenticatedCommandService.execute(
            session,
            actor=actor,
            command_name="template_audit.propose",
            idempotency_key=inputs.idempotency_key,
            payload=inputs.model_dump(mode="json", exclude={"idempotency_key"}),
            response_model=SavedAudit,
            operation=operation,
        )
        return {
            "result": await cls.get(session, actor, outcome.value.report_id),
            "replayed": outcome.replayed,
        }

    @classmethod
    async def decide(cls, session, actor, report_id, finding_id, inputs):
        if actor.channel != "manager":
            raise HTTPException(403, "Decisions require an explicit Manager action")
        from services.command_transaction import command_transaction

        initial = await cls.report(session, actor, report_id)
        async with command_transaction(session):
            (
                issuer,
                template,
                customer,
                links,
                versions,
            ) = await TemplateAuditService.scope(
                session,
                actor,
                initial.legal_entity_id,
                initial.template_id,
                initial.customer_id,
                lock=True,
            )
            row = await cls.report(session, actor, report_id, lock=True)
            _, context_hash = TemplateAuditService.context(
                issuer, template, customer, links, versions
            )
            cls.guard(row, inputs, context_hash)
            if not any(
                v.id == row.version_id and v.checksum_sha256 == row.source_hash
                for v in versions
            ):
                raise HTTPException(409, "Reviewed source version changed")
            findings = [dict(f) for f in row.findings]
            finding = next((f for f in findings if f["id"] == finding_id), None)
            if finding is None:
                raise HTTPException(404, "Finding not found")
            finding["decision_history"] = [
                *finding.get("decision_history", []),
                {
                    "from": finding["status"],
                    "to": inputs.status,
                    "reason": inputs.reason,
                    "actor": actor.staff_user_id,
                    "at": _now().isoformat(),
                    "channel": actor.channel,
                    "source_hash": row.source_hash,
                    "context_hash": context_hash,
                    "legal_sources_hash": row.legal_sources_hash,
                    "proposed_text": finding.get("proposed_text"),
                    "applicability": finding.get("applicability"),
                },
            ]
            finding["status"] = inputs.status
            row.findings, row.revision, row.updated_at = (
                findings,
                row.revision + 1,
                _now(),
            )
            session.add(row)
        return await cls.get(session, actor, report_id)
