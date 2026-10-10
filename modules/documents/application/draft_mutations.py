"""Change or discard an unnumbered draft while preserving issued history."""

from copy import deepcopy
from datetime import date, datetime, time
from decimal import Decimal

from sqlmodel import select

from models import (
    DocumentArtifact,
    DocumentExternalEditSession,
    MaintenanceActPreparation,
)
from modules.documents.domain import (
    ActTerms,
    B2C_NATIVE_DOCUMENT_TYPES,
    BUSINESS_TERMS_DOCUMENT_TYPES,
    BusinessDocumentTerms,
    ConsumerDocumentTerms,
    PaymentScheduleItem,
    TransportTerms,
)
from modules.documents.domain.participant_statement import ParticipantStatement
from .business_context import build_business_document_context
from .consumer_context import build_consumer_document_context
from .draft_parameters import (
    TERM_GROUPS,
    draft_revision,
    json_terms,
    read_draft_parameters,
    saved_total,
)
from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from .external_edit_support import external_edit_lease_is_live
from .installation_context import staged_template_is_supported
from .transport_context import build_transport_document_context


def domain_terms(name, data):
    if data is None:
        return None
    data = dict(data)
    for key in (
        "delivery_deadline",
        "performance_deadline",
        "valid_until",
        "acceptance_deadline",
    ):
        if data.get(key):
            data[key] = date.fromisoformat(str(data[key]))
    if name == "business_terms":
        data["payment_schedule"] = tuple(
            PaymentScheduleItem(
                **{**item, "share_percent": Decimal(str(item["share_percent"]))}
            )
            for item in data.get("payment_schedule", [])
        )
    return {
        "business_terms": BusinessDocumentTerms,
        "consumer_terms": ConsumerDocumentTerms,
        "act_terms": ActTerms,
        "transport_terms": TransportTerms,
        "participant_statement": ParticipantStatement,
    }[name](**data)


class ManagedDocumentDraftMutationService:
    @staticmethod
    async def _load(session, *, tenant_scope, document_id, lock=False):
        from .lifecycle_service import ManagedDocumentService

        document = await ManagedDocumentService._get_scoped_document(
            session, tenant_scope=tenant_scope, document_id=document_id, for_update=lock
        )
        if document is None:
            raise ManagedDocumentNotFoundError("Документ не найден")
        if lock:
            await session.refresh(document)
        if (
            document.status != "draft"
            or document.official_number
            or document.issued_at
            or document.official_date
        ):
            raise ManagedDocumentConflictError(
                "Изменять и удалять можно только черновик до присвоения официального номера"
            )
        if (
            not document.internal_reference
            or not document.template_version_id
            or not document.render_snapshot
        ):
            raise ManagedDocumentConflictError(
                "Документ не относится к управляемым черновикам"
            )
        if lock:
            await ManagedDocumentService._get_mutable_scoped_order(
                session,
                tenant_scope=tenant_scope,
                order_id=document.order_id,
                require_mutable=True,
            )
        artifacts = list(
            (
                await session.execute(
                    select(DocumentArtifact).where(
                        DocumentArtifact.tenant_id == tenant_scope.tenant_id,
                        DocumentArtifact.order_document_id == document_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        if any(item.kind != "source_docx" for item in artifacts):
            raise ManagedDocumentConflictError(
                "У документа уже есть файлы выпуска; сохраните его в истории"
            )
        return document, artifacts

    @staticmethod
    async def _discard_editable_copies(session, artifacts):
        if not artifacts:
            return
        sessions = list(
            (
                await session.execute(
                    select(DocumentExternalEditSession)
                    .where(
                        DocumentExternalEditSession.document_artifact_id.in_(
                            [item.id for item in artifacts]
                        )
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        if any(external_edit_lease_is_live(item) for item in sessions):
            raise ManagedDocumentConflictError(
                "Дождитесь завершения синхронизации черновика"
            )
        for item in sessions:
            await session.delete(item)
        await session.flush()
        for item in artifacts:
            await session.delete(item)
        await session.flush()

    @classmethod
    async def get(cls, session, *, tenant_scope, document_id):
        document, artifacts = await cls._load(
            session, tenant_scope=tenant_scope, document_id=document_id
        )
        return {
            **read_draft_parameters(document),
            "revision": draft_revision(document, artifacts),
            "has_editable_copy": bool(artifacts),
            "total_amount": str(saved_total(document.render_snapshot)),
            "order_conditions": document.render_snapshot.get("values", {}).get(
                "contract.additional_conditions"
            ),
        }

    @classmethod
    async def update(
        cls,
        session,
        *,
        tenant_scope,
        document_id,
        changes,
        expected_revision,
        reset_editable_copy=False
    ):
        from .lifecycle_service import ManagedDocumentService

        document, artifacts = await cls._load(
            session, tenant_scope=tenant_scope, document_id=document_id, lock=True
        )
        if draft_revision(document, artifacts) != expected_revision:
            raise ManagedDocumentConflictError(
                "Параметры уже изменены в другой вкладке. Откройте их заново"
            )
        scopes = {
            "business_terms": document.doc_type in BUSINESS_TERMS_DOCUMENT_TYPES,
            "consumer_terms": document.doc_type in B2C_NATIVE_DOCUMENT_TYPES,
            "act_terms": document.doc_type == "act",
            "transport_terms": document.doc_type in {"tn2", "ttn1"},
            "participant_statement": document.doc_type == "participant_statement",
        }
        if any(name in changes and not allowed for name, allowed in scopes.items()):
            raise ValueError("Эти параметры не соответствуют типу документа")
        current = read_draft_parameters(document)
        changed = {
            key: value for key, value in changes.items() if value != current.get(key)
        }
        if not changed:
            return document
        rebuild = bool(set(changed) - {"issue_date"})
        if rebuild and artifacts and not reset_editable_copy:
            raise ManagedDocumentConflictError(
                "Изменение этих параметров требует пересборки рабочей копии. Подтвердите замену ручных правок"
            )
        snapshot = deepcopy(document.render_snapshot)
        values, meta = snapshot["values"], snapshot.setdefault("meta", {})
        parameters = {**current, **changed}
        new_date = date.fromisoformat(parameters["issue_date"])
        values["document.issued_on"] = new_date.strftime("%d.%m.%Y")
        values["document.issue_city"] = str(parameters.get("issue_city") or "").strip()
        meta["issue_city"] = values["document.issue_city"]
        terms = {name: domain_terms(name, parameters.get(name)) for name in TERM_GROUPS}
        if set(changed) & {"business_terms", "act_terms"}:
            if parameters.get("business_terms", {}).get("contract_scenario") != (
                current.get("business_terms") or {}
            ).get("contract_scenario"):
                raise ManagedDocumentConflictError(
                    "Для другого сценария договора создайте черновик с подходящим шаблоном"
                )
            context = build_business_document_context(
                document_type=document.doc_type,
                terms=terms["business_terms"],
                act_terms=terms["act_terms"],
                order_additional_conditions=values.get(
                    "contract.additional_conditions"
                ),
                total_amount=saved_total(snapshot),
            )
            values.update(context.values)
            snapshot["conditions"].update(context.conditions)
            snapshot["table_rows"].update(context.table_rows)
        if "consumer_terms" in changed:
            from .template_selection import load_document_template_version

            _, version = await load_document_template_version(
                session, tenant_scope=tenant_scope, document=document
            )
            if terms[
                "consumer_terms"
            ].installation_two_stages and not staged_template_is_supported(
                version.placeholder_schema or {}
            ):
                raise ManagedDocumentConflictError(
                    "Выбранная версия шаблона не поддерживает монтаж в два этапа"
                )
            context = build_consumer_document_context(
                document_type=document.doc_type,
                terms=terms["consumer_terms"],
                seller_requisites={
                    "offer_url": values.get("offer.url"),
                    "offer_version": values.get("offer.version"),
                    "offer_published_on": values.get("offer.published_on"),
                },
                total_amount=saved_total(snapshot),
            )
            values.update(context.values)
            snapshot["conditions"].update(context.conditions)
        if "transport_terms" in changed:
            values.update(
                build_transport_document_context(terms["transport_terms"]).values
            )
        if "participant_statement" in changed:
            values.update(terms["participant_statement"].values())
        meta["draft_parameters"] = {
            name: json_terms(terms[name]) for name in TERM_GROUPS
        }
        if rebuild:
            await cls._discard_editable_copies(session, artifacts)
            document.google_edit_url = None
            document.google_file_id = None
        document.date = datetime.combine(new_date, time.min)
        document.render_snapshot = snapshot
        session.add(document)
        await ManagedDocumentService._commit(
            session, "Не удалось сохранить параметры черновика"
        )
        await session.refresh(document)
        return document

    @classmethod
    async def delete(cls, session, *, tenant_scope, document_id):
        from .lifecycle_service import ManagedDocumentService

        document, artifacts = await cls._load(
            session, tenant_scope=tenant_scope, document_id=document_id, lock=True
        )
        if await session.scalar(
            select(MaintenanceActPreparation.id).where(
                MaintenanceActPreparation.document_id == document_id
            )
        ):
            raise ManagedDocumentConflictError(
                "Черновик сохраняет связь с замечаниями ТО. Подготовьте новую версию явным действием"
            )
        await cls._discard_editable_copies(session, artifacts)
        await session.delete(document)
        await ManagedDocumentService._commit(
            session, "Не удалось удалить черновик документа"
        )
