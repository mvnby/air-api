"""Transactional waiting: no financial, document, assignment or visit side effects."""

from datetime import datetime
from models import Order, OrderStatus, TenantAuditEvent
from sqlalchemy import select
from services.order_board_money import board_money
from core.request_context import current_request_id
from services.command_transaction import command_transaction
from services.tenant_entity_access_service import TenantEntityAccessService
from services.order_workflow_revision import bump_order_workflow_revision


class OrderWaitingError(ValueError):
    def __init__(self, message, status_code=409, code="order_waiting_conflict"):
        super().__init__(message)
        self.status_code, self.code = status_code, code


class OrderWaitingService:
    @classmethod
    async def execute(cls, session, order_id, payload, *, auth, tenant_scope):
        if tenant_scope.demo_read_only:
            raise OrderWaitingError(
                "Демонстрационная компания доступна только для чтения", 403
            )
        async with command_transaction(session):
            order = await TenantEntityAccessService.get_order(
                session,
                order_id,
                tenant_scope=tenant_scope,
                for_update=True,
                populate_existing=True,
            )
            if order is None:
                raise OrderWaitingError("Заказ не найден", 404)
            if order.workflow_revision != payload.expected_revision:
                raise OrderWaitingError(
                    "Заказ, этапы или оплаты изменились. Обновите заказ и повторите действие."
                )
            if order.status not in (OrderStatus.NEGOTIATION, OrderStatus.EXECUTION):
                raise OrderWaitingError(
                    "Ожидание доступно только для переговоров и работ"
                )
            fields = (
                "is_on_hold",
                "on_hold_reason",
                "on_hold_reason_code",
                "on_hold_started_at",
                "next_followup_date",
            )
            before = {field: getattr(order, field) for field in fields}
            if payload.action == "wait":
                if not payload.reason_code:
                    raise OrderWaitingError("Выберите причину ожидания", 400)
                note = (payload.note or "").strip() or None
                if payload.reason_code == "other" and not note:
                    raise OrderWaitingError(
                        "Укажите пояснение для причины «Другое»", 400
                    )
                if not order.is_on_hold:
                    order.on_hold_started_at = datetime.now()
                order.is_on_hold = True
                order.on_hold_reason_code = payload.reason_code
                order.on_hold_reason = note
                if "next_followup_date" in payload.model_fields_set:
                    from services.order_service import OrderService

                    order.next_followup_date = OrderService._normalize_naive_datetime(
                        payload.next_followup_date
                    )
            else:
                order.is_on_hold = False
                order.on_hold_started_at = None
                # Preserve historical free text/code and the agreed contact.
            after = {field: getattr(order, field) for field in fields}
            changed = {
                key: {"before": cls._json(value), "after": cls._json(after[key])}
                for key, value in before.items()
                if value != after[key]
            }
            if changed:
                session.add(order)
                await bump_order_workflow_revision(session, order)
                changed["workflow_revision"] = {
                    "before": payload.expected_revision,
                    "after": order.workflow_revision,
                }
                session.add(
                    TenantAuditEvent(
                        tenant_id=tenant_scope.tenant_id,
                        storefront_id=tenant_scope.storefront_id,
                        actor_staff_user_id=auth.staff_user_id,
                        actor_username=auth.username,
                        request_id=current_request_id(),
                        action="order.waiting_changed",
                        entity_type="order",
                        entity_id=order.id,
                        change_set=changed,
                    )
                )
            # Freeze under the same parent lock. No read-side legacy repairs.
            from services.order_projection_service import OrderProjectionService

            result = await OrderProjectionService.get_order_detail_for_manager(
                session, order_id, tenant_scope=tenant_scope, repair_legacy_state=False
            )
            # Return the same current scalar money as the board, without persisting
            # the read-side calculate_totals cache during a waiting command.
            visible = (
                select(Order.id)
                .where(Order.id == order_id)
                .cte("waiting_visible_order")
            )
            money = board_money(visible)
            values = (await session.execute(select(money))).mappings().one()
            result.update(
                {key: float(value or 0) for key, value in values.items() if key != "id"}
            )
        return result

    @staticmethod
    def _json(value):
        return value.isoformat() if isinstance(value, datetime) else value
