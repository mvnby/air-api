"""Compose native order commands with a scoped edit revision and durable retries."""

import hashlib
import json

from fastapi import HTTPException
from pydantic import BaseModel

from api_contracts.bot_order_desk import BotOrderDesk, BotOrderPrepareDocument, BotOrderQuote
from api_contracts.bot_order_issuance import BotIssueDocument
from api_contracts.bot_order_payments import BotRecordPayment
from api_contracts.bot_order_proposal import BotProposalChange
from api_contracts.bot_order_reserve import BotReserveChange
from services.authenticated_command_service import AuthenticatedCommandService
from services.bot_order_documents import draft_issuers, prepare_document, read_documents, saved_proposal
from services.bot_order_followup import apply_followup, read_followup
from services.bot_order_issuance import issue_order_document, read_issuance
from services.bot_order_payments import apply_payment, read_payments
from services.bot_order_proposal import apply_proposal, read_proposals
from services.bot_order_reserve import apply_reserve, read_reserve
from services.bot_workspace_projection import order_row
from services.bot_workspace_service import scoped_order_money
from services.order_projection_service import OrderProjectionService
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.tenant_entity_access_service import TenantEntityAccessService


class OrderReceipt(BaseModel):
    order_id: int


async def _visible(session, ws, order_id, *, lock=False):
    order = await TenantEntityAccessService.get_order(
        session, order_id, tenant_scope=ws.scope, for_update=lock, populate_existing=True,
    )
    if order is None or order.status == "new_lead":
        raise HTTPException(404, "Заказ не найден.")


async def _read(session, ws, order_id):
    detail = await OrderProjectionService.get_order_detail_for_manager(
        session, order_id, tenant_scope=ws.scope, repair_legacy_state=False,
    )
    if detail is None or detail["status"] == "new_lead":
        raise HTTPException(404, "Заказ не найден.")
    detail.update(await scoped_order_money(session, ws.scope, order_id, legacy_ungrouped_only=True))
    followup = await read_followup(session, ws.actor, detail)
    proposals = await read_proposals(session, ws.actor, detail)
    row = order_row(detail)
    data = dict(
        id=order_id, title=row.title, status=detail["status"], status_label=row.status,
        currency="BYN", manager_url=ws.url(f"orders/{order_id}"), followup=followup,
        **proposals,
        documents=await read_documents(session, ws.scope, order_id),
        document_issuers=await draft_issuers(session, ws.scope, detail, followup, proposals["proposals"]),
        reserve=await read_reserve(session, ws.actor, detail),
        payments=await read_payments(session, ws.actor, detail),
        issuance=await read_issuance(session, ws.actor, detail),
    )
    desk = BotOrderDesk(**data, revision="0" * 64)
    # Manager writes to lines, customer data and documents don't all bump workflow_revision.
    revision_data = [detail["workflow_revision"], str(detail["balance_due"]), desk.model_dump(
        mode="json", exclude={"revision": True, "manager_url": True, "payments": {"received_on_max"}},
    )]
    serialized = json.dumps(revision_data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    desk.revision = hashlib.sha256(serialized.encode()).hexdigest()
    return desk, detail


async def get_order_desk(session, ws, order_id):
    desk, _ = await _read(session, ws, order_id)
    return desk


def require_revision(desk, expected):
    if desk.revision != expected:
        raise HTTPException(409, "Заказ изменился. Обновите карточку и проверьте свои изменения.")


async def change_order(session, ws, order_id, request):
    # Even a replay requires current access to this order.
    await _visible(session, ws, order_id)
    change = request.change

    async def load_order():
        await _visible(session, ws, order_id, lock=True)
        return await _read(session, ws, order_id)

    if isinstance(change, BotIssueDocument):
        await issue_order_document(session, ws.actor, order_id, request, load_order=load_order)
        return await get_order_desk(session, ws, order_id)

    async def apply():
        desk, detail = await load_order()
        require_revision(desk, request.expected_revision)
        if isinstance(change, BotOrderPrepareDocument):
            await prepare_document(session, ws.scope, desk, change)
        elif isinstance(change, BotProposalChange):
            await apply_proposal(session, ws.actor, order_id, change, detail)
        elif isinstance(change, BotReserveChange):
            await apply_reserve(session, ws.actor, order_id, change, detail)
        elif isinstance(change, BotRecordPayment):
            await apply_payment(session, ws.actor, order_id, change, detail)
        else:
            await apply_followup(session, ws.actor, order_id, change, detail)
        return PublicWriteCommandResponse(value=OrderReceipt(order_id=order_id), resource_type="order", resource_id=order_id)

    await AuthenticatedCommandService.execute(
        session, actor=ws.actor, command_name="order.telegram_change",
        idempotency_key=str(request.idempotency_key),
        payload={"order_id": order_id, "expected_revision": request.expected_revision,
                 "change": change.model_dump(mode="json", exclude_unset=True)},
        response_model=OrderReceipt, operation=apply,
    )
    return await get_order_desk(session, ws, order_id)


def _money(value):
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " BYN"


async def quote(session, ws, order_id, proposal_id, revision):
    desk = await get_order_desk(session, ws, order_id)
    require_revision(desk, revision)
    proposal = saved_proposal(desk, proposal_id)
    lines = [f"Предложение по заказу № {order_id}"]
    for title, items in (("Оборудование", proposal.product_lines), ("Работы и услуги", proposal.service_lines)):
        if items:
            lines.extend(["", title])
            for item in items:
                for row in getattr(item, "display_lines", None) or [item]:
                    lines.append(f"{row.title} — {row.quantity} × {_money(row.unit_price)} = {_money(row.line_total)}")
                    if row.description:
                        lines.append(row.description)
    lines.extend(["", f"Итого · {_money(proposal.total_amount)}"])
    return BotOrderQuote(text="\n".join(lines))
