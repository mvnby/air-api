"""Explicit human classification of related delivery document originals."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Order, OrderDocument
from models.tenancy import TenantScope
from schemas_manager_orders import ManagerCustomerReconciliationEventRelationPayload
from services.customer_reconciliation_projection import (
    ACTIVE_STATUSES, DELIVERY_DOC_TYPES, EVENT_RELATIONS_META_KEY,
    document_identity, event_fingerprint,
)
from services.tenant_scope_service import storefront_scope_clause


class ReconciliationEventRelationError(ValueError):
    pass


async def confirm_event_relation(
    session: AsyncSession,
    *,
    customer_id: int,
    payload: ManagerCustomerReconciliationEventRelationPayload,
    tenant_scope: TenantScope,
    confirmed_by: str,
) -> dict:
    if tenant_scope.demo_read_only:
        raise ReconciliationEventRelationError("Демо-данные доступны только для просмотра")
    ids = sorted(set(payload.document_ids))
    if len(ids) != len(payload.document_ids) or len(ids) < 2 or len(ids) > 10:
        raise ReconciliationEventRelationError("Укажите от 2 до 10 разных документов")
    statement = (
        select(OrderDocument)
        .join(Order, Order.id == OrderDocument.order_id)
        .where(
            OrderDocument.id.in_(ids),
            Order.customer_id == customer_id,
            storefront_scope_clause(Order, tenant_scope),
        )
        .order_by(OrderDocument.id)
        .with_for_update(of=OrderDocument)
    )
    docs = list((await session.execute(statement)).scalars().all())
    if len(docs) != len(ids) or len({doc.order_id for doc in docs}) != 1:
        raise ReconciliationEventRelationError("Документы должны принадлежать одному заказу этого контрагента")
    superseded_ids = set((await session.execute(
        select(OrderDocument.replaces_document_id).where(
            OrderDocument.order_id == docs[0].order_id,
            OrderDocument.replaces_document_id.in_(ids),
            OrderDocument.status.in_(("issued", "sent", "signed")),
        )
    )).scalars().all())
    identities = [document_identity(doc) for doc in docs]
    for doc, identity in zip(docs, identities):
        if (doc.doc_type not in DELIVERY_DOC_TYPES or doc.status not in ACTIVE_STATUSES
                or doc.id in superseded_ids
                or identity["identity_source"] not in {"official", "confirmed_legacy"}
                or identity["amount"] is None):
            raise ReconciliationEventRelationError("Сначала подтвердите действующие оригиналы и суммы")
    if payload.relation == "same":
        if len({identity["date"].date() for identity in identities}) != 1:
            raise ReconciliationEventRelationError("Для одной операции даты документов должны совпадать")
        if len({identity["amount"] for identity in identities}) != 1:
            raise ReconciliationEventRelationError("Для одной операции суммы документов должны совпадать")
        if len({identity["contract_id"] for identity in identities}) != 1:
            raise ReconciliationEventRelationError("Для одной операции договор документов должен совпадать")
    confirmed_at = datetime.now(timezone.utc)
    record = {
        "document_ids": ids,
        "relation": payload.relation,
        "reason": payload.reason.strip(),
        "confirmed_at": confirmed_at.isoformat(),
        "confirmed_by": confirmed_by,
        "fingerprints": {str(doc.id): event_fingerprint(doc) for doc in docs},
    }
    key = "-".join(map(str, ids))
    for doc in docs:
        meta = dict(doc.scope_meta or {})
        relations = dict(meta.get(EVENT_RELATIONS_META_KEY) or {})
        relations[key] = record
        meta[EVENT_RELATIONS_META_KEY] = relations
        doc.scope_meta = meta
        session.add(doc)
    await session.commit()
    return {"document_ids": ids, "relation": payload.relation, "confirmed_at": confirmed_at}
