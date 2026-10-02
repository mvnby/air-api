"""Scoped persistence; extraction can never overwrite a manager's proposal."""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from models import Order
from models.tenancy import TenantScope
from schemas_business_document_terms import BusinessDocumentTermsPayload
from schemas_commercial_terms import CommercialSourceTerm, ManagerCommercialTermsResponse, ManagerCommercialTermsUpdate
from services.command_transaction import command_transaction
from services.commercial_terms_extraction import extract_commercial_terms, suggest_document_terms
from services.tenant_entity_access_service import TenantEntityAccessService


class CommercialTermsRevisionConflict(ValueError):
    pass


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _source_state(order: Order) -> tuple[dict, dict, bool]:
    meta = _dict(order.technical_meta)
    raw_state = meta.get("commercial_terms")
    state = _dict(raw_state)
    malformed = (order.technical_meta is not None and not isinstance(order.technical_meta, dict)) or (raw_state is not None and not isinstance(raw_state, dict))
    return meta, state, malformed


def _saved_terms(state: dict) -> tuple[list[CommercialSourceTerm], bool]:
    raw_terms = state.get("customer_requested")
    if raw_terms is None:
        return [], False
    if not isinstance(raw_terms, list):
        return [], True
    terms = []
    malformed = len(raw_terms) > 100
    for value in raw_terms[:100]:
        try:
            terms.append(CommercialSourceTerm.model_validate(value))
        except (ValueError, TypeError):
            malformed = True
    return terms, malformed


def stored_source_terms(order: Order) -> list[CommercialSourceTerm]:
    meta, state, malformed = _source_state(order)
    terms, invalid_terms = _saved_terms(state)
    malformed = malformed or invalid_terms
    if not terms:
        raw_email = meta.get("email_source_text")
        if isinstance(raw_email, str):
            terms.extend(extract_commercial_terms(raw_email, source="Письмо заказчика"))
        tender = _dict(_dict(meta.get("belzakupki")).get("tender"))
        if isinstance(tender.get("description"), str):
            terms.extend(extract_commercial_terms(tender["description"], source="Описание закупки"))
    if malformed:
        for term in terms:
            term.issues.append("Часть сохранённых условий повреждена; проверьте оригинал")
    return terms


def _revision(state: dict) -> int:
    revision = state.get("revision", 0)
    return revision if type(revision) is int and revision >= 0 else 0


def commercial_terms_summary(order: Order) -> list[str]:
    return [term.evidence for term in stored_source_terms(order)][:3]


def commercial_terms_response(order: Order, *, terms: list[CommercialSourceTerm] | None = None) -> ManagerCommercialTermsResponse:
    meta, state, malformed = _source_state(order)
    _, invalid_terms = _saved_terms(state)
    source_terms = stored_source_terms(order) if terms is None else terms
    warnings = list(dict.fromkeys(issue for term in source_terms for issue in term.issues))
    incomplete_source = bool(meta.get("email_source_text_truncated") or state.get("source_truncated"))
    if incomplete_source:
        warnings.append("Текст источника неполный; проверьте оригинал перед подтверждением условий")
    proposed = None
    if state.get("proposed") is not None:
        try:
            proposed = BusinessDocumentTermsPayload.model_validate(state["proposed"])
        except (ValueError, TypeError):
            malformed = True
    malformed = malformed or invalid_terms or ("revision" in state and (type(state["revision"]) is not int or state["revision"] < 0))
    if malformed:
        warnings.append("Сохранённые условия повреждены; проверьте и сохраните их заново")
    suggested = None if incomplete_source or malformed else suggest_document_terms(source_terms)
    if source_terms and suggested is None:
        warnings.append("Условия требуют проверки: полный график оплаты не определён")
    return ManagerCommercialTermsResponse(order_id=order.id, revision=_revision(state),
        customer_requested=source_terms, proposed=proposed, confirmed=state.get("confirmed") is True and proposed is not None,
        suggested=suggested, warnings=warnings)


def store_source_terms(order: Order, terms: list[CommercialSourceTerm]) -> None:
    original_meta, original_state, _ = _source_state(order)
    meta = dict(original_meta)
    state = dict(original_state)
    # Extraction owns evidence only. Proposal, confirmation and revision stay intact.
    state["customer_requested"] = [term.model_dump(mode="json") for term in terms]
    meta["commercial_terms"] = state
    order.technical_meta = meta
    flag_modified(order, "technical_meta")


class OrderCommercialTermsService:
    @staticmethod
    async def order(session: AsyncSession, *, order_id: int, scope: TenantScope, lock: bool = False) -> Order:
        order = await TenantEntityAccessService.get_order(session, order_id, tenant_scope=scope, for_update=lock, populate_existing=lock)
        if order is None:
            raise LookupError("Заказ не найден")
        return order

    @classmethod
    async def read(cls, session: AsyncSession, *, order_id: int, scope: TenantScope) -> ManagerCommercialTermsResponse:
        return commercial_terms_response(await cls.order(session, order_id=order_id, scope=scope))

    @classmethod
    async def update(cls, session: AsyncSession, *, order_id: int, scope: TenantScope, payload: ManagerCommercialTermsUpdate, username: str) -> ManagerCommercialTermsResponse:
        if scope.demo_read_only:
            raise PermissionError("Демонстрационный доступ: изменения запрещены")
        async with command_transaction(session):
            order = await cls.order(session, order_id=order_id, scope=scope, lock=True)
            meta, original_state, _ = _source_state(order)
            state = dict(original_state)
            if _revision(state) != payload.expected_revision:
                raise CommercialTermsRevisionConflict("Условия изменены другим менеджером; обновите данные")
            state.update(proposed=payload.proposed.model_dump(mode="json"), confirmed=payload.confirmed,
                revision=payload.expected_revision + 1, reviewed_by=username)
            # Materialize existing source evidence before saving the independent proposal.
            state.setdefault("customer_requested", [term.model_dump(mode="json") for term in stored_source_terms(order)])
            order.technical_meta = {**meta, "commercial_terms": state}
            flag_modified(order, "technical_meta")
            session.add(order)
            response = commercial_terms_response(order)
        return response

    @classmethod
    async def extract(cls, session: AsyncSession, *, order_id: int, scope: TenantScope, attachment_ids: list[int] | None = None) -> ManagerCommercialTermsResponse:
        if scope.demo_read_only:
            raise PermissionError("Демонстрационный доступ: изменения запрещены")
        async with command_transaction(session):
            order = await cls.order(session, order_id=order_id, scope=scope, lock=True)
            source_terms = stored_source_terms(order)
            if attachment_ids:
                from services.email_contract_review_service import EmailContractReviewService, extract_contract
                for attachment_id in dict.fromkeys(attachment_ids):
                    content = await EmailContractReviewService.load_content(session, order_id=order_id, attachment_id=attachment_id, tenant_scope=scope)
                    if content is None:
                        raise LookupError("Оригинал письма не найден")
                    filename, binary = content
                    extracted = await asyncio.to_thread(extract_contract, filename, binary)
                    for page_index, page_text in enumerate(extracted.pages, 1):
                        source = f"{filename}, страница {page_index}" if extracted.page_numbers_available else filename
                        source_terms.extend(extract_commercial_terms(page_text, source=source))
            unique = {(term.source, term.evidence, term.kind): term for term in source_terms}
            store_source_terms(order, list(unique.values()))
            session.add(order)
            response = commercial_terms_response(order)
        return response
