"""Scoped CRM reads use the same queue, customer and personal-task services as Manager."""

from dataclasses import dataclass
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api_contracts.bot_workspace import BotWorkspaceDetail, BotWorkspaceList
from core.command_actor import CommandActor
from core.config import settings
from models import Customer, Order, OrderProductLink, Product
from schemas_leads_inbox import InboxReadPayload
from schemas_personal_tasks import PersonalTaskStatusPayload
from services import bot_workspace_projection as view
from services.bot_api_access import require_bot_manager_actor
from services.customer_service import CustomerService
from services.leads_inbox_command_service import LeadsInboxCommandService
from services.leads_inbox_service import LeadsInboxService
from services.order_board_money import board_money
from services.order_board_projection import OrderBoardProjection
from services.order_service import OrderService
from services.personal_task_service import PersonalTaskService
from services.raw_lead_inbox_service import RawLeadInboxService
from services.tenant_entity_access_service import TenantEntityAccessService as Access
from services.unified_inbox_service import UnifiedInboxService


@dataclass(frozen=True)
class Workspace:
    actor: CommandActor
    site: str

    @property
    def scope(self):
        return self.actor.tenant_scope

    def url(self, path, **params):
        query = urlencode({**params, "company": self.scope.tenant_id, "site": self.site})
        return f"{settings.MANAGER_BASE_URL.rstrip('/')}/{path}?{query}"


async def workspace_for(session, telegram_id):
    actor, selection = await require_bot_manager_actor(session, telegram_id)
    return Workspace(actor, selection.storefront_slug)


FILTERS = {
    "incoming": ("active", "unread", "archive"),
    "orders": ("active", "mine", "waiting", "history", "all"),
    "customers": ("all", "favorites", "individual", "individual_entrepreneur", "company"),
    "tasks": ("active", "today", "overdue", "completed", "cancelled"),
}


async def list_workspace(session, ws, section, *, query, selected_filter, page, limit):
    filters = FILTERS[section]
    selected = selected_filter or filters[0]
    if selected not in filters:
        raise ValueError("Фильтр недоступен в этом разделе")
    if section == "incoming":
        result = await UnifiedInboxService.get_leads_inbox(
            session, tenant_scope=ws.scope, username=ws.actor.username, page=page, limit=limit, search=query,
            scope="archive" if selected == "archive" else "active", unread_only=selected == "unread",
        )
        items, total = [view.incoming_row(item) for item in result.items], result.total
    elif section == "orders":
        result = await OrderBoardProjection.page(
            session, tenant_scope=ws.scope, segment="all", queue="all" if selected == "mine" else selected,
            assigned_to_me=selected == "mine", staff_user_id=ws.actor.staff_user_id, search=query, page=page, limit=limit,
        )
        items, total = [view.order_row(item.model_dump()) for item in result["items"]], result["total"]
    elif section == "customers":
        result = await CustomerService.list_for_manager(
            session, tenant_scope=ws.scope, page=page, limit=limit, search=query, only_with_orders=False,
            only_favorites=selected == "favorites", customer_type=selected if selected in view.PARTIES else None,
        )
        items, total = [view.customer_row(item) for item in result["items"]], result["meta"]["total"]
    else:
        result = await PersonalTaskService.list(
            session, actor=ws.actor, task_filter=selected, search=query, offset=(page - 1) * limit, limit=limit,
        )
        items, total = [view.task_row(item) for item in result.items], result.total
    return BotWorkspaceList(items=items, total=total, page=page, limit=limit)


async def incoming_item(session, ws, item_id, kind):
    if kind == "lead":
        return await RawLeadInboxService.detail(session, item_id, username=ws.actor.username, tenant_scope=ws.scope)
    if kind == "order":
        return await LeadsInboxService.detail(session, order_id=item_id, username=ws.actor.username, tenant_scope=ws.scope)
    raise ValueError("Укажите тип входящего обращения")


async def scoped_order_money(session, scope, item_id, *, legacy_ungrouped_only: bool = False):
    visible = (select(Order.id).outerjoin(Customer, Customer.id == Order.customer_id)
               .where(Order.id == item_id, Access.order_clause(scope), Access.order_customer_clause(scope))
               .cte("workspace_order"))
    money = board_money(visible, legacy_ungrouped_only=legacy_ungrouped_only)
    sums = (await session.execute(select(money.c.total_amount, money.c.balance_due))).mappings().one_or_none()
    if sums is None:
        raise LookupError("Заказ не найден")
    return sums


async def _order_detail(session, ws, item_id):
    order = await Access.get_order(session, item_id, tenant_scope=ws.scope, options=(
        selectinload(Order.customer), selectinload(Order.proposals),
        selectinload(Order.product_links).selectinload(OrderProductLink.product).load_only(Product.title),
    ))
    if order is None or order.status == "new_lead":
        raise LookupError("Заказ не найден")
    sums = await scoped_order_money(session, ws.scope, item_id)
    customer = order.customer
    meta = order.technical_meta or {}
    return {
        **sums, "proposals": view.order_equipment(order), "id": item_id, "title": OrderService._display_order_title(order), "status": OrderService._status_value(order.status),
        "is_on_hold": order.is_on_hold, "delivery_address": order.delivery_address,
        "comment": order.comment, "contact_name": meta.get("contact_name"), "contact_phone": meta.get("contact_phone"),
        "measurement_date": order.measurement_date, "installation_date": order.installation_date,
        "next_followup_date": order.next_followup_date,
        "customer": {"id": customer.id, "name": customer.name, "phone": customer.phone} if customer else None,
    }


async def workspace_detail(session, ws, section, item_id, kind=None):
    if kind is not None and section != "incoming":
        raise ValueError("Тип источника нужен только во входящих")
    writable = not ws.scope.demo_read_only
    actions = []
    proposals = []
    version = customer_id = None
    description = None
    if section == "incoming":
        item = await incoming_item(session, ws, item_id, kind)
        row, facts = view.incoming_row(item), view.incoming_facts(item)
        description = item.original_text or item.comment or item.summary
        url = ws.url("leads", kind=kind, itemId=item_id)
        customer_id = item.customer_id
        if writable:
            actions.append("mark_unread" if item.is_read else "mark_read")
            if item.source_kind == "customer_request" and not item.archive:
                source = (await Access.get_lead(session, item_id, tenant_scope=ws.scope) if kind == "lead" else
                          await Access.get_order(session, item_id, tenant_scope=ws.scope))
                if source:
                    version = source.version if kind == "lead" else source.workflow_revision
                    actions.append("service_order")
    elif section == "orders":
        data = await _order_detail(session, ws, item_id)
        row, facts = view.order_row(data), view.order_facts(data)
        proposals = data["proposals"]
        description = data.get("comment")
        customer_id = (data.get("customer") or {}).get("id")
        url = ws.url(f"orders/{item_id}")
    elif section == "customers":
        data = await CustomerService.get_for_manager(session, item_id, tenant_scope=ws.scope)
        if not data or data["is_archived"]:
            raise LookupError("Клиент не найден")
        row, facts = view.customer_row(data), view.customer_facts(data)
        url = ws.url("customers/profile", customerId=item_id)
        if writable:
            actions.append("customer_draft")
    else:
        item = await PersonalTaskService.get(session, actor=ws.actor, task_id=item_id)
        row, facts = view.task_row(item), view.task_facts(item)
        description = item.description
        if len(item.text) > len(row.title):
            description = "\n".join(part for part in (item.text, description) if part)
        version, url = item.version, ws.url("tasks", taskId=item_id)
        if writable:
            actions.append("complete" if item.status == "active" else "reopen")
    return BotWorkspaceDetail(item=row, proposals=proposals, facts=facts, description=(description or "")[:8000] or None,
                              manager_url=url, actions=actions, version=version, customer_id=customer_id)


async def set_incoming_read(session, ws, item_id, payload):
    if payload.kind == "lead":
        await RawLeadInboxService.mutate(session, item_id, username=ws.actor.username, tenant_scope=ws.scope,
                                         action="read", payload=InboxReadPayload(is_read=payload.is_read))
    else:
        await LeadsInboxCommandService.read(session, order_id=item_id, username=ws.actor.username,
                                            tenant_scope=ws.scope, is_read=payload.is_read)
    return await workspace_detail(session, ws, "incoming", item_id, payload.kind)


async def change_task_status(session, ws, item_id, payload):
    method = PersonalTaskService.complete if payload.action == "complete" else PersonalTaskService.reopen
    await method(session, actor=ws.actor, task_id=item_id, payload=PersonalTaskStatusPayload(expected_version=payload.expected_version),
                 idempotency_key=payload.idempotency_key)
    # A replayed receipt can predate a reassignment. Check today's visibility before returning any task fields.
    return await workspace_detail(session, ws, "tasks", item_id)
