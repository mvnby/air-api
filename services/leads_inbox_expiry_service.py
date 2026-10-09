"""Bounded automatic expiry of trusted tender submission deadlines only."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_
from sqlmodel import select

from models import Customer, LeadSource, Order, OrderStatus
from models.leads_inbox import InboxTriageState
from models.tenancy import TenantScope
from services.command_transaction import command_transaction
from services.leads_inbox_command_service import LeadsInboxCommandService
from services.leads_inbox_service import LeadsInboxService
from services.tenant_entity_access_service import TenantEntityAccessService


class LeadsInboxExpiryService:
    @staticmethod
    def trusted_deadline(order):
        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        if order.lead_source == LeadSource.EMAIL:
            confirmed = meta.get("inbox_tender")
            if (isinstance(confirmed, dict) and confirmed.get("confirmed") is True
                    and confirmed.get("is_tender") is True and confirmed.get("confirmed_by")
                    and confirmed.get("confirmed_at")):
                return LeadsInboxService.deadline_value(meta)
            return None
        if order.lead_source != LeadSource.BELZAKUPKI or not order.source_fingerprint:
            return None
        provider = meta.get("belzakupki")
        if not isinstance(provider, dict) or not provider.get("last_synced_at"):
            return None
        tender = provider.get("tender")
        if not isinstance(tender, dict) or not tender.get("source") or not tender.get("external_id"):
            return None
        # The authenticated opportunity API's deadline_at is the submission
        # deadline. Other explicitly typed dates (delivery/contract) are excluded.
        if tender.get("deadline_kind", "submission") != "submission":
            return None
        return LeadsInboxService.deadline_value(meta)

    @classmethod
    def eligible(cls, order, state, *, now, context=None, has_publications=False):
        if order.status != OrderStatus.NEW_LEAD or order.linked_order_id is not None or (state and state.archived_at):
            return None
        if has_publications or (context and context.stage in ("submitted", "completed")):
            return None
        deadline = context.deadline_at if context and context.deadline_manual else cls.trusted_deadline(order)
        if deadline is None or now < deadline + timedelta(hours=24):
            return None
        restored = state.restored_deadline_at if state else None
        if restored is not None and restored.astimezone(timezone.utc) == deadline:
            return None
        return deadline

    @classmethod
    async def run(cls, session, *, execute=False, now=None, tenant_scope=None, limit=100, after_id=0):
        if execute:
            async with command_transaction(session):
                return await cls._run(session, execute=True, now=now, tenant_scope=tenant_scope, limit=limit, after_id=after_id)
        return await cls._run(session, execute=False, now=now, tenant_scope=tenant_scope, limit=limit, after_id=after_id)

    @classmethod
    async def _run(cls, session, *, execute=False, now=None, tenant_scope=None, limit=100, after_id=0):
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        limit = min(100, max(1, int(limit)))
        query = (select(Order.id, Order.tenant_id, Order.storefront_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .outerjoin(InboxTriageState, and_(InboxTriageState.entity_kind == "order", InboxTriageState.entity_id == Order.id))
            .where(Order.id > after_id, Order.status == OrderStatus.NEW_LEAD,
                Order.lead_source.in_([LeadSource.BELZAKUPKI, LeadSource.EMAIL]), Order.linked_order_id.is_(None),
                InboxTriageState.archived_at.is_(None))
            .order_by(Order.id).limit(limit))
        if tenant_scope:
            query = query.where(TenantEntityAccessService.order_clause(tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope))
        roots = (await session.execute(query)).all()
        candidates = []
        for root in roots:
            scope = tenant_scope or TenantScope(tenant_id=root.tenant_id, storefront_id=root.storefront_id, is_system=False)
            # Import, qualification and expiry serialize on the same Order lock.
            order = await TenantEntityAccessService.get_order(session, root.id, tenant_scope=scope,
                for_update=execute, populate_existing=True)
            if not order:
                continue
            state = (await session.execute(select(InboxTriageState).where(InboxTriageState.entity_kind == "order",
                InboxTriageState.entity_id == root.id).execution_options(populate_existing=True))).scalar_one_or_none()
            from models.tender_workflow import TenderWorkflowLink
            from services.tender_workflow_service import TenderWorkflowService
            context = await TenderWorkflowService.context(session, root.id, scope)
            publication = (await session.execute(select(TenderWorkflowLink.publication_order_id).where(
                TenderWorkflowLink.price_order_id == root.id, TenderWorkflowService.scope(TenderWorkflowLink, scope))
                .limit(1))).first()
            deadline = cls.eligible(order, state, now=now, context=context, has_publications=publication is not None)
            if deadline is None:
                continue
            candidates.append({"order_id": root.id, "tenant_id": root.tenant_id,
                "storefront_id": root.storefront_id, "deadline_at": deadline.isoformat()})
            if execute:
                state = state or LeadsInboxCommandService.state(order)
                state.outcome, state.reason, state.note = "deadline_expired", None, None
                state.archived_at, state.archived_by = now, "system:tender-deadline"
                session.add(state)
                session.add(LeadsInboxCommandService.event(order, kind="archive", actor="system:tender-deadline",
                    outcome="deadline_expired", created_at=now))
        if execute:
            await session.flush()
        return {"mode": "execute" if execute else "report_only", "scanned": len(roots),
            "candidates": candidates, "archived": len(candidates) if execute else 0,
            "next_after_id": roots[-1].id if len(roots) == limit else 0}
