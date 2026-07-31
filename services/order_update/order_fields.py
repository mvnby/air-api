"""Order-owned field and assignment mutations for Manager updates."""

from datetime import datetime

from sqlalchemy import delete
from sqlmodel import select
from sqlalchemy.orm.attributes import flag_modified

from models import OrderInstaller, OrderStatus, PaymentCurrency
from models.common import ClosingResult, EquipmentStatus
from services.document_role_service import DocumentRoleService
from services.order_service import OrderService
from services.order_update.context import OrderUpdateContext


async def apply_order_fields(context: OrderUpdateContext) -> None:
    session = context.session
    order = context.order
    payload = context.payload
    fields_set = context.fields_set

    if "status" in fields_set and payload.status is not None:
        try:
            order.status = OrderStatus(payload.status)
        except ValueError as exc:
            raise ValueError(f"Invalid status: {payload.status}") from exc
        if (
            order.status != context.previous_status
            or not getattr(order, "status_changed_at", None)
        ):
            order.status_changed_at = datetime.now()
        if order.status == OrderStatus.CLOSED and not order.closing_result:
            order.closing_result = ClosingResult.WON.value
        if order.status != OrderStatus.CLOSED:
            order.closing_result = None
            order.reject_reason = None
            order.closed_at = None
    if "title" in fields_set:
        order.title = OrderService._clean_order_title(payload.title)
    if "workflow_type" in fields_set and payload.workflow_type is not None:
        order.workflow_type = OrderService._normalize_workflow_type(
            payload.workflow_type,
            order.workflow_type,
        )
    if "repair_meta" in fields_set:
        default_status = (
            OrderService.REPAIR_DEFAULT_STATUS
            if OrderService._normalize_workflow_type(order.workflow_type) == "repair"
            else None
        )
        OrderService._set_repair_meta(
            order,
            payload.repair_meta,
            default_status=default_status,
        )
        flag_modified(order, "technical_meta")
    if "manager_labels" in fields_set:
        OrderService._set_manager_labels(order, payload.manager_labels)
    if "next_followup_date" in fields_set:
        order.next_followup_date = OrderService._normalize_naive_datetime(
            payload.next_followup_date
        )
    if "measurement_date" in fields_set:
        order.measurement_date = OrderService._normalize_naive_datetime(
            payload.measurement_date
        )
    if "installation_date" in fields_set:
        order.installation_date = OrderService._normalize_naive_datetime(
            payload.installation_date
        )
    if "comment" in fields_set:
        order.comment = payload.comment
    if "is_paid" in fields_set and payload.is_paid is not None:
        order.is_paid = payload.is_paid
    if "customer_delivery_address" in fields_set:
        order.delivery_address = payload.customer_delivery_address
    if "document_role_type" in fields_set:
        order.document_role_type = DocumentRoleService.nullable_role_type(
            payload.document_role_type
        )
    if "closing_result" in fields_set:
        if payload.closing_result is None:
            order.closing_result = None
        else:
            try:
                order.closing_result = ClosingResult(payload.closing_result).value
            except ValueError as exc:
                raise ValueError(
                    f"Invalid closing_result: {payload.closing_result}"
                ) from exc
    if "reject_reason" in fields_set:
        order.reject_reason = payload.reject_reason
    if "is_on_hold" in fields_set and payload.is_on_hold is not None:
        order.is_on_hold = payload.is_on_hold
    if "on_hold_reason" in fields_set:
        order.on_hold_reason = payload.on_hold_reason
    if "measurement_required" in fields_set and payload.measurement_required is not None:
        order.measurement_required = payload.measurement_required
    if "measurer_id" in fields_set:
        if payload.measurer_id is not None and payload.measurer_id != order.measurer_id:
            await OrderService._ensure_assignable_legacy_executor(
                session,
                int(payload.measurer_id),
                tenant_scope=context.tenant_scope,
            )
        order.measurer_id = payload.measurer_id
    if "measurement_result" in fields_set:
        order.measurement_result = payload.measurement_result
    if "additional_conditions" in fields_set:
        value = (payload.additional_conditions or "").strip()
        order.additional_conditions = value or None
    if "negotiation_status" in fields_set and payload.negotiation_status is not None:
        OrderService._set_negotiation_status(order, payload.negotiation_status)
    if "execution_status" in fields_set and payload.execution_status is not None:
        OrderService._set_execution_status(order, payload.execution_status)
    if "proposal_status" in fields_set and payload.proposal_status is not None:
        order.proposal_status = payload.proposal_status
        if payload.proposal_status == "sent" and not order.proposal_sent_at:
            order.proposal_sent_at = datetime.now()
    if "proposal_sent_at" in fields_set:
        order.proposal_sent_at = OrderService._normalize_naive_datetime(
            payload.proposal_sent_at
        )
    if (
        "execution_without_payment" in fields_set
        and payload.execution_without_payment is not None
    ):
        order.execution_without_payment = bool(payload.execution_without_payment)
    if "execution_without_payment_reason" in fields_set:
        order.execution_without_payment_reason = OrderService._clean_optional_text(
            payload.execution_without_payment_reason
        )
    if (
        "auto_execution_on_payment" in fields_set
        and payload.auto_execution_on_payment is not None
    ):
        order.auto_execution_on_payment = bool(payload.auto_execution_on_payment)
    if "auto_close_on_payment" in fields_set and payload.auto_close_on_payment is not None:
        order.auto_close_on_payment = bool(payload.auto_close_on_payment)

    _apply_workflow_defaults(context)

    if "equipment_status" in fields_set and payload.equipment_status is not None:
        try:
            order.equipment_status = EquipmentStatus(payload.equipment_status)
        except ValueError as exc:
            raise ValueError(
                f"Invalid equipment_status: {payload.equipment_status}"
            ) from exc
    if (
        "standard_install_kit_issued" in fields_set
        and payload.standard_install_kit_issued is not None
    ):
        order.standard_install_kit_issued = payload.standard_install_kit_issued

    _apply_currency_fields(context)

    if "status" in fields_set and order.status == OrderStatus.CLOSED and not order.closed_at:
        order.closed_at = datetime.now()

    if "installer_id" in fields_set:
        await _replace_installer(context)


def _apply_workflow_defaults(context: OrderUpdateContext) -> None:
    order = context.order
    payload = context.payload
    fields_set = context.fields_set

    if order.status == OrderStatus.EXECUTION and order.proposal_status != "approved":
        order.proposal_status = "approved"
    if order.status == OrderStatus.EXECUTION:
        if "execution_status" not in fields_set:
            if "installation_date" in fields_set and order.installation_date:
                OrderService._set_execution_status(order, "scheduled")
            elif not getattr(order, "execution_status_changed_at", None):
                OrderService._set_execution_status(
                    order,
                    OrderService._infer_execution_status(order),
                )
    else:
        order.execution_without_payment = False
        order.execution_without_payment_reason = None

    if order.status == OrderStatus.NEGOTIATION and "negotiation_status" not in fields_set:
        if "measurement_required" in fields_set and order.measurement_required:
            OrderService._set_negotiation_status(order, "awaiting_visit")
        elif "proposal_status" in fields_set and order.proposal_status == "sent":
            OrderService._set_negotiation_status(order, "proposal_sent")
        elif "proposal_status" in fields_set and order.proposal_status == "approved":
            OrderService._set_negotiation_status(order, "awaiting_payment")
    if (
        order.status == OrderStatus.NEGOTIATION
        and not getattr(order, "negotiation_status_changed_at", None)
    ):
        order.negotiation_status_changed_at = datetime.now()
    if (
        order.status == OrderStatus.NEGOTIATION
        and OrderService._normalize_negotiation_status(
            getattr(order, "negotiation_status", None)
        )
        != context.previous_negotiation_status
    ):
        order.negotiation_status_changed_at = datetime.now()
    if (
        order.status == OrderStatus.EXECUTION
        and not getattr(order, "execution_status_changed_at", None)
    ):
        order.execution_status_changed_at = datetime.now()
    if (
        order.status == OrderStatus.EXECUTION
        and OrderService._normalize_execution_status(
            getattr(order, "execution_status", None)
        )
        != context.previous_execution_status
    ):
        order.execution_status_changed_at = datetime.now()


def _apply_currency_fields(context: OrderUpdateContext) -> None:
    order = context.order
    payload = context.payload
    fields_set = context.fields_set

    if "target_currency" in fields_set:
        new_target_currency = payload.target_currency
        if new_target_currency is not None:
            new_target_currency = OrderService._normalize_payment_currency(
                new_target_currency
            )
        if new_target_currency is None:
            has_foreign_payments = any(
                OrderService._normalize_payment_currency(payment.currency)
                != PaymentCurrency.BYN
                for payment in order.payments
            )
            if has_foreign_payments:
                raise ValueError(
                    "Cannot disable currency mode while foreign-currency payments exist"
                )
        order.target_currency = new_target_currency
        context.currency_fields_changed = True
    if "target_currency_amount" in fields_set:
        order.target_currency_amount = payload.target_currency_amount
        context.currency_fields_changed = True


async def _replace_installer(context: OrderUpdateContext) -> None:
    session = context.session
    payload = context.payload
    order_id = context.order_id

    existing_installer_ids_result = await session.execute(
        select(OrderInstaller.installer_id).where(OrderInstaller.order_id == order_id)
    )
    existing_installer_ids = set(existing_installer_ids_result.scalars().all())
    if (
        getattr(payload, "installer_id", None) is not None
        and payload.installer_id not in existing_installer_ids
    ):
        await OrderService._ensure_assignable_legacy_executor(
            session,
            int(payload.installer_id),
            tenant_scope=context.tenant_scope,
        )
    await session.execute(
        delete(OrderInstaller).where(OrderInstaller.order_id == order_id)
    )
    if getattr(payload, "installer_id", None) is not None:
        session.add(
            OrderInstaller(
                order_id=order_id,
                installer_id=payload.installer_id,
            )
        )
