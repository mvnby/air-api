"""Map scoped payment history and register actual receipts through the Manager command."""

from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_order_payments import BotOrderPayment, BotOrderPayments, BotRecordPayment
from core.command_actor import CommandActor
from models.common import ClosingResult, OrderStatus
from services.inbox_eligibility import require_unarchived_inbox
from services.order_payment_command_service import OrderPaymentCommandService
from services.order_proposal_command_service import OrderProposalCommandService
from services.service_estimate_money import decimal_value, money


_MINSK = ZoneInfo("Europe/Minsk")


def _workflow_notice(detail: dict) -> str | None:
    if detail["is_on_hold"]:
        return "Оплата отразится в заказе. Заказ останется в ожидании."
    starts_execution = (
        detail["status"] == OrderStatus.NEGOTIATION
        and detail["auto_execution_on_payment"]
        and not detail["maintenance_source_order_id"]
    )
    closes_order = (
        (detail["status"] == OrderStatus.EXECUTION or starts_execution)
        and detail["auto_close_on_payment"]
        and detail["execution_status"] == "awaiting_payment"
        and all(stage["status"] == "completed" for stage in detail["work_stages"])
    )
    if closes_order:
        return "При полной оплате заказ может завершиться автоматически."
    if starts_execution:
        return "При полной оплате заказ автоматически перейдёт в работу."
    return None


def _unavailable_reason(actor: CommandActor, detail: dict, total: Decimal) -> str | None:
    if actor.tenant_scope.demo_read_only:
        return "В демонстрационном режиме доступен просмотр оплат."
    if detail["status"] not in {OrderStatus.NEGOTIATION, OrderStatus.EXECUTION} or detail["closing_result"] == ClosingResult.LOST:
        return "Оплату можно записать в открытом заказе."
    if total <= 0:
        return "Добавьте позиции в заказ, чтобы записать оплату."
    return None


async def read_payments(session: AsyncSession, actor: CommandActor, detail: dict) -> BotOrderPayments:
    """Read only the payment rows already projected beneath the scoped order."""
    total = money(detail["total_amount"])
    unavailable = _unavailable_reason(actor, detail, total)
    if unavailable is None:
        try:
            await require_unarchived_inbox(session, "order", detail["id"])
        except ValueError as exc:
            unavailable = str(exc)
    entries = [
        BotOrderPayment(
            id=row["id"], amount=money(row["amount"]), currency=row["currency"], type=row["type"],
            received_on=row["date"].date(), bank_confirmed=row["bank_receipt_id"] is not None,
            comment=row["comment"],
        )
        for row in sorted(detail["payments"], key=lambda row: (row["date"], row["id"]), reverse=True)
    ]
    result = BotOrderPayments(
        total_amount=total, total_payments=money(detail["total_payments"]), balance_due=money(detail["balance_due"]),
        entries=entries, currencies=["BYN"] if not unavailable else [],
        received_on_max=datetime.now(_MINSK).date(),
        can_record=unavailable is None, record_unavailable_reason=unavailable,
        workflow_notice=_workflow_notice(detail) if unavailable is None else None,
    )
    currency = detail["target_currency"]
    target = decimal_value(detail["target_currency_amount"])
    if currency in {"USD", "EUR"} and total > 0 and target > 0:
        paid = decimal_value(detail["target_currency_payments"])
        result.target_currency = currency
        result.target_currency_amount = money(target)
        result.target_currency_payments = money(paid)
        result.target_currency_balance_due = money(max(Decimal("0"), target - paid))
        result.exchange_rate = (total / target).quantize(Decimal("0.00000001")).normalize()
        if result.can_record:
            result.currencies.append(currency)
    return result


async def apply_payment(
    session: AsyncSession, actor: CommandActor, order_id: int, change: BotRecordPayment, detail: dict,
) -> None:
    """Apply inside the actor's command transaction and current order lock."""
    if detail["id"] != order_id:
        raise LookupError("Заказ не найден")
    available = await read_payments(session, actor, detail)
    if not available.can_record:
        raise ValueError(available.record_unavailable_reason)
    if not change.confirmed:
        raise ValueError("Подтвердите, что оплата уже получена")
    if change.received_on > available.received_on_max:
        raise ValueError("Дата поступления не может быть в будущем")
    if change.currency not in available.currencies:
        raise ValueError("Для этой валюты нужна сохранённая сумма сделки в Kitlane")
    scope = actor.tenant_scope
    if not any(not proposal["is_archived"] for proposal in detail["proposals"]):
        # Match the legacy order desk totals before canonical financial refresh.
        await OrderProposalCommandService.ensure_default_order_proposal(session, order_id, tenant_scope=scope)
    now = datetime.now(_MINSK).replace(tzinfo=None)
    received_at = now if change.received_on == now.date() else datetime.combine(change.received_on, time.min)
    await OrderPaymentCommandService.add_payment(session, order_id, change, tenant_scope=scope, received_at=received_at)
