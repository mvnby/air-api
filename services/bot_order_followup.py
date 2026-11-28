"""Apply Telegram follow-up commands through the Manager order and customer services."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_order_followup import (
    BotOrderAssignCustomer,
    BotOrderCreateCustomer,
    BotOrderFollowup,
    BotOrderFollowupChange,
    BotOrderSetDetails,
    BotOrderSetSchedule,
    BotOrderTransition,
    BotOrderWorkflowAction,
    ScheduleField,
)
from api_contracts.order_waiting import ManagerOrderWaitingCommand
from core.command_actor import CommandActor
from core.input_validation import validate_optional_email, validate_optional_phone, validate_optional_unp
from models import MaintenanceContinuation, OrderStatus
from models.order_site import OrderSite
from schemas_manager_orders import ManagerOrderUpdatePayload
from services.customer_creation_service import CustomerCreationService
from services.inbox_eligibility import require_unarchived_inbox
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_update.command import OrderUpdateCommandService
from services.order_waiting_service import OrderWaitingService
from services.tenant_entity_access_service import TenantEntityAccessService


_MINSK = ZoneInfo("Europe/Minsk")
_ACTIVE_STATUSES = (OrderStatus.NEGOTIATION, OrderStatus.EXECUTION)
_SCHEDULE_FIELDS: tuple[ScheduleField, ...] = (
    "measurement_date", "installation_date", "next_followup_date",
)
_NEGOTIATION_ACTIONS = {
    "awaiting_offer": "Ждёт предложение",
    "awaiting_visit": "Ждёт выезд",
    "proposal_sent": "Ожидаем ответ",
    "awaiting_signature": "Ожидаем договор",
    "awaiting_payment": "Ожидаем оплату",
    "follow_up": "Требуется уточнение",
}
_EXECUTION_ACTIONS = {
    "order_equipment": "Заказать товар",
    "awaiting_equipment": "Ждём оборудование",
    "needs_schedule": "Назначить работы",
    "scheduled": "Работы назначены",
    "work_done": "Работы выполнены",
    "awaiting_documents": "Оформление документов",
    "awaiting_payment": "Ждём оплату за работы",
}
_POST_WORK_STATUSES = {"work_done", "awaiting_documents", "awaiting_payment"}


def _workflow_actions(detail: dict, *, has_active_customer: bool, continuation: bool):
    if detail.get("is_on_hold"):
        return [BotOrderWorkflowAction(action="resume", label="Возобновить работу", requires_confirmation=True)]

    actions = [
        BotOrderWorkflowAction(
            action="wait", label="Перевести в ожидание", requires_confirmation=True, requires_reason_code=True,
        )
    ]
    if continuation:
        # Follow the dedicated consent and execution workflow in Manager for linked maintenance.
        return actions

    negotiating = detail["status"] == OrderStatus.NEGOTIATION
    for status, label in _NEGOTIATION_ACTIONS.items():
        if negotiating and status == detail.get("negotiation_status"):
            continue
        actions.append(BotOrderWorkflowAction(
            action=f"negotiation:{status}", label=label, requires_confirmation=not negotiating,
        ))

    balance_due = detail["balance_due"]
    if not negotiating or has_active_customer:
        for status, label in _EXECUTION_ACTIONS.items():
            if not negotiating and status == detail.get("execution_status"):
                continue
            if negotiating and status in _POST_WORK_STATUSES - {"awaiting_payment"}:
                continue
            unpaid = status != "awaiting_payment" and balance_due > 0 and not detail.get("execution_without_payment")
            actions.append(BotOrderWorkflowAction(
                action=f"execution:{status}", label=label,
                requires_confirmation=negotiating or unpaid or status == "work_done",
                requires_reason=unpaid,
            ))
    if not negotiating and has_active_customer and balance_due <= 0:
        actions.append(BotOrderWorkflowAction(action="closed_won", label="Завершить заказ", requires_confirmation=True))
    actions.append(BotOrderWorkflowAction(
        action="closed_lost", label="Закрыть с отказом", requires_confirmation=True, requires_reason=True,
    ))
    return actions


async def read_followup(
    session: AsyncSession, actor: CommandActor, detail: dict, *, writable: bool = True,
) -> BotOrderFollowup:
    """Project actions from the scoped Manager detail and its current board balance."""
    current_customer = detail.get("customer")
    data = {field: detail[field] for field in BotOrderFollowup.model_fields if field in detail}
    if detail["status"] == OrderStatus.NEGOTIATION:
        data["workflow_status_label"] = _NEGOTIATION_ACTIONS.get(detail.get("negotiation_status"))
    elif detail["status"] == OrderStatus.EXECUTION:
        data["workflow_status_label"] = _EXECUTION_ACTIONS.get(detail.get("execution_status"))
    elif detail["status"] == OrderStatus.CLOSED:
        data["workflow_status_label"] = {"won": "Завершён", "lost": "Отказ"}.get(detail.get("closing_result"))
    writable = writable and not actor.tenant_scope.demo_read_only and detail["status"] in _ACTIVE_STATUSES
    if not writable:
        return BotOrderFollowup(**data)
    order_id = detail["id"]
    try:
        await require_unarchived_inbox(session, "order", order_id)
    except ValueError:
        return BotOrderFollowup(**data)

    continuation_order_id = await session.scalar(
        select(MaintenanceContinuation.order_id)
        .where(or_(MaintenanceContinuation.order_id == order_id, MaintenanceContinuation.source_order_id == order_id))
        .order_by((MaintenanceContinuation.order_id == order_id).desc())
        .limit(1)
    )
    has_locked_customer = (
        continuation_order_id is not None
        or bool(detail.get("documents"))
        or detail.get("customer_contract_id") is not None
        or await session.scalar(select(OrderSite.id).where(OrderSite.order_id == order_id).limit(1)) is not None
    )
    has_active_customer = False
    if current_customer is not None:
        linked = await TenantEntityAccessService.get_customer(
            session, current_customer["id"], tenant_scope=actor.tenant_scope,
        )
        has_active_customer = linked is not None and not linked.is_archived
    data.update(
        can_edit_details=True,
        can_assign_customer=not has_locked_customer,
        can_create_customer=not has_locked_customer and current_customer is None,
        customer_assignment_requires_confirmation=not has_locked_customer and current_customer is not None,
        schedule_fields=["next_followup_date"] if continuation_order_id == order_id else list(_SCHEDULE_FIELDS),
        workflow_actions=_workflow_actions(
            detail, has_active_customer=has_active_customer, continuation=continuation_order_id == order_id,
        ),
    )
    return BotOrderFollowup(**data)


async def apply_followup(
    session: AsyncSession, actor: CommandActor, order_id: int, change: BotOrderFollowupChange, detail: dict,
) -> None:
    """Apply one restricted change under the caller's order lock and command transaction."""
    available = await read_followup(session, actor, detail)
    if not available.can_edit_details:
        raise ValueError("Заказ недоступен для изменения")
    if isinstance(change, BotOrderTransition):
        values = await _transition(session, actor, order_id, change, detail, available)
        if values is None:
            return
        if (values.get("status") == OrderStatus.EXECUTION or values.get("closing_result") == "won") and not any(
            not proposal["is_archived"] for proposal in detail["proposals"]
        ):
            # Native financial finalization must use the same variant the manager confirmed.
            await OrderProposalCommandService._load_order_for_write(session, order_id, tenant_scope=actor.tenant_scope)
    elif isinstance(change, BotOrderSetSchedule):
        if change.field not in available.schedule_fields:
            raise ValueError("Эта дата недоступна для изменения")
        values = _schedule_fields(change, detail)
    elif isinstance(change, BotOrderSetDetails):
        values = change.model_dump(exclude_unset=True, exclude={"kind"})
        if "contact_phone" in values:
            values["contact_phone"] = validate_optional_phone(values["contact_phone"])
        if "delivery_address" in values:
            values["customer_delivery_address"] = values.pop("delivery_address")
    else:
        values = await _assign_customer(session, actor, change, available)
        if not values:
            return

    updated = await OrderUpdateCommandService.update_order_for_manager(
        session, order_id, ManagerOrderUpdatePayload(**values), tenant_scope=actor.tenant_scope,
        repair_legacy_state=False, reconcile_unchanged_payments=False,
    )
    if updated is None:
        raise LookupError("Заказ не найден")


async def _assign_customer(
    session: AsyncSession,
    actor: CommandActor,
    change: BotOrderAssignCustomer | BotOrderCreateCustomer,
    available: BotOrderFollowup,
) -> dict:
    scope = actor.tenant_scope
    if isinstance(change, BotOrderCreateCustomer):
        if not available.can_create_customer:
            raise ValueError("Создание клиента недоступно для этого заказа")
        customer = await CustomerCreationService.create_record_for_manager(
            session, tenant_scope=scope,
            payload={
                "name": change.name,
                "type": change.customer_type,
                "phone": validate_optional_phone(change.phone),
                "email": validate_optional_email(change.email),
                "inn": validate_optional_unp(change.inn),
            },
        )
    else:
        if not available.can_assign_customer:
            raise ValueError("Смена клиента недоступна для этого заказа. Откройте заказ в Kitlane.")
        if available.customer and available.customer.id == change.customer_id:
            return {}
        if available.customer_assignment_requires_confirmation and not change.confirmed:
            raise ValueError("Подтвердите смену клиента заказа")
        customer = await TenantEntityAccessService.get_customer(session, change.customer_id, tenant_scope=scope, for_update=True)
        if customer is None or customer.is_archived:
            raise LookupError("Клиент не найден")
    return {"customer_id": customer.id, "customer_branch_id": None}


def _schedule_fields(change: BotOrderSetSchedule, detail: dict) -> dict:
    value: datetime | None = change.date
    if value is not None and value.tzinfo is not None:
        value = value.astimezone(_MINSK).replace(tzinfo=None)
    values = {change.field: value}
    if value is not None and change.field == "measurement_date" and not detail.get("measurement_required"):
        values["measurement_required"] = True
    if (
        change.field == "installation_date" and detail["status"] == OrderStatus.EXECUTION
        and detail.get("execution_status") in _POST_WORK_STATUSES
    ):
        # Editing a historical visit date must not roll completed work back to scheduled.
        values["execution_status"] = detail["execution_status"]
    return values


async def _transition(
    session: AsyncSession, actor: CommandActor, order_id: int, change: BotOrderTransition,
    detail: dict, available: BotOrderFollowup,
) -> dict | None:
    option = next((item for item in available.workflow_actions if item.action == change.action), None)
    if option is None:
        raise ValueError("Это действие недоступно для текущего состояния заказа")
    if option.requires_confirmation and not change.confirmed:
        raise ValueError("Подтвердите изменение состояния заказа")
    if option.requires_reason_code and not change.reason_code:
        raise ValueError("Выберите причину ожидания")
    if (option.requires_reason or change.reason_code == "other") and not change.reason:
        raise ValueError("Укажите причину")
    if change.action in {"wait", "resume"}:
        await OrderWaitingService.execute(
            session, order_id,
            ManagerOrderWaitingCommand(
                action=change.action, expected_revision=detail["workflow_revision"],
                reason_code=change.reason_code, note=change.reason,
            ), auth=actor, tenant_scope=actor.tenant_scope,
        )
        return None
    if change.action == "closed_lost":
        return {"status": "closed", "closing_result": "lost", "reject_reason": change.reason}
    if change.action == "closed_won":
        return {"status": "closed", "closing_result": "won", "reject_reason": None}

    stage, status = change.action.split(":", 1)
    values = {stage + "_status": status}
    if stage != detail["status"]:
        values["status"] = stage
    if stage == "negotiation" and status == "awaiting_visit":
        values["measurement_required"] = True
    if stage == "execution" and option.requires_reason:
        values.update(execution_without_payment=True, execution_without_payment_reason=change.reason)
    return values
