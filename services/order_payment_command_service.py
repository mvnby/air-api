"""Transactional commands for order payments and bank-receipt reconciliation."""

from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import BankReceipt, Customer, Order, Payment, PaymentCurrency, PaymentType
from services.command_transaction import command_transaction
from services.order_service import OrderService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import TenantScope


class OrderPaymentCommandService:
    @staticmethod
    async def _list_payments(
        session: AsyncSession,
        order_id: int,
    ) -> List[Dict[str, Any]]:
        result = await session.execute(
            select(Payment)
            .where(Payment.order_id == order_id)
            .options(selectinload(Payment.bank_receipt))
            .order_by(Payment.date.desc())
        )
        return [
            OrderService._map_payment(payment)
            for payment in result.scalars().all()
        ]

    @staticmethod
    async def add_payment(
        session: AsyncSession,
        order_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> List[Dict[str, Any]]:
        async with command_transaction(session):
            order = await TenantEntityAccessService.get_order(
                session,
                order_id,
                tenant_scope=tenant_scope,
                for_update=True,
            )
            if not order:
                raise ValueError("Order not found")

            try:
                payment_type = PaymentType(payload.type)
            except ValueError as exc:
                raise ValueError(f"Invalid payment type: {payload.type}") from exc

            currency = OrderService._normalize_payment_currency(
                payload.currency
                if hasattr(payload, "currency")
                else PaymentCurrency.BYN
            )
            if currency != PaymentCurrency.BYN and order.target_currency != currency:
                raise ValueError(
                    "Foreign-currency payment requires matching order target currency"
                )

            session.add(
                Payment(
                    order_id=order_id,
                    amount=payload.amount,
                    currency=currency,
                    type=payment_type,
                    comment=payload.comment,
                )
            )
            await session.flush()
            await OrderService._refresh_order_financials(session, order)
            session.add(order)

        return await OrderPaymentCommandService._list_payments(session, order_id)

    @staticmethod
    async def delete_payment(
        session: AsyncSession,
        order_id: int,
        payment_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> List[Dict[str, Any]]:
        async with command_transaction(session):
            order = await TenantEntityAccessService.get_order(
                session,
                order_id,
                tenant_scope=tenant_scope,
                for_update=True,
            )
            if not order:
                raise ValueError("Order not found")

            payment = await session.get(Payment, payment_id)
            if not payment or payment.order_id != order_id:
                raise ValueError("Payment not found on this order")

            bank_receipt_id = (
                int(payment.bank_receipt_id) if payment.bank_receipt_id else None
            )
            affected_order_ids = {int(order_id)}

            if bank_receipt_id:
                all_linked_ids = list(
                    (
                        await session.execute(
                            select(Payment.id).where(
                                Payment.bank_receipt_id == bank_receipt_id
                            )
                        )
                    ).scalars()
                )
                linked_payments_result = await session.execute(
                    select(Payment)
                    .join(Order, Order.id == Payment.order_id)
                    .outerjoin(Customer, Customer.id == Order.customer_id)
                    .where(
                        Payment.bank_receipt_id == bank_receipt_id,
                        TenantEntityAccessService.order_clause(tenant_scope),
                        TenantEntityAccessService.order_customer_clause(
                            tenant_scope
                        ),
                    )
                )
                linked_payments = list(linked_payments_result.scalars().all())
                if len(linked_payments) != len(all_linked_ids):
                    raise ValueError("Bank receipt spans a tenant boundary")
                deleted_payment_ids = [
                    int(item.id or 0) for item in linked_payments if item.id
                ]
                for linked_payment in linked_payments:
                    if linked_payment.order_id:
                        affected_order_ids.add(int(linked_payment.order_id))
                    await session.delete(linked_payment)

                receipt = await session.get(BankReceipt, bank_receipt_id)
                if receipt:
                    metadata = dict(receipt.match_meta or {})
                    metadata.update(
                        {
                            "manual_status": "requires_review",
                            "manual_reason": "payment_deleted_from_order",
                            "previous_status": receipt.status,
                            "previous_matched_order_id": receipt.matched_order_id,
                            "previous_matched_payment_id": receipt.matched_payment_id,
                            "previous_matched_payment_ids": deleted_payment_ids
                            or None,
                        }
                    )
                    receipt.status = "requires_review"
                    receipt.matched_order_id = None
                    receipt.matched_payment_id = None
                    receipt.match_meta = metadata
                    session.add(receipt)
            else:
                await session.delete(payment)
            await session.flush()

            for affected_order_id in affected_order_ids:
                affected_order = await TenantEntityAccessService.get_order(
                    session,
                    affected_order_id,
                    tenant_scope=tenant_scope,
                )
                if not affected_order:
                    continue
                await OrderService._refresh_order_financials(
                    session,
                    affected_order,
                )
                affected_order.is_paid = affected_order.balance_due <= 0.01
                session.add(affected_order)

        return await OrderPaymentCommandService._list_payments(session, order_id)
