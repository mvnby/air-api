from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import BankReceipt, Order, Payment, PaymentType
from services.bank_receipt_service import BankReceiptService
from services.order_service import OrderService


class BankReceiptAllocationService:
    @staticmethod
    async def get_totals(
        session: AsyncSession,
        receipt_ids: list[int],
    ) -> dict[int, dict[str, float | int]]:
        ids = sorted({int(receipt_id) for receipt_id in receipt_ids if receipt_id})
        if not ids:
            return {}
        result = await session.execute(
            select(
                Payment.bank_receipt_id,
                func.coalesce(func.sum(Payment.amount), 0),
                func.count(Payment.id),
            )
            .where(Payment.bank_receipt_id.in_(ids))
            .group_by(Payment.bank_receipt_id)
        )
        return {
            int(receipt_id): {
                "allocated_amount": BankReceiptService._money(allocated_amount),
                "allocation_count": int(allocation_count or 0),
            }
            for receipt_id, allocated_amount, allocation_count in result.all()
            if receipt_id
        }

    @staticmethod
    async def get_detail(
        session: AsyncSession,
        *,
        receipt_id: int,
    ) -> dict[str, Any]:
        receipt = await session.get(BankReceipt, receipt_id)
        if not receipt:
            raise ValueError("Bank receipt not found")

        payment_result = await session.execute(
            select(Payment)
            .where(Payment.bank_receipt_id == receipt_id)
            .order_by(Payment.id.asc())
        )
        payments = list(payment_result.scalars().all())
        allocation_by_order: dict[int, float] = {}
        for payment in payments:
            allocation_by_order[int(payment.order_id)] = BankReceiptService._money(
                allocation_by_order.get(int(payment.order_id), 0) + payment.amount
            )

        linked_order_ids = set(allocation_by_order)
        orders = await BankReceiptService._load_receipt_candidate_orders(
            session,
            receipt,
            allow_closed_order_ids=linked_order_ids,
        )
        items: list[dict[str, Any]] = []
        for order in orders:
            order_id = int(order.id or 0)
            current_allocation = allocation_by_order.get(order_id, 0.0)
            other_payments = BankReceiptService._money(float(order.total_payments or 0) - current_allocation)
            balance_before = BankReceiptService._money(max(0.0, float(order.total_amount or 0) - other_payments))
            if balance_before <= BankReceiptService.EXACT_AMOUNT_TOLERANCE and not current_allocation:
                continue
            items.append(
                {
                    "order_id": order_id,
                    "title": order.title,
                    "customer_name": order.customer.name if order.customer else None,
                    "status": order.status.value if hasattr(order.status, "value") else str(order.status),
                    "created_at": order.created_at,
                    "total_amount": BankReceiptService._money(order.total_amount),
                    "total_payments": BankReceiptService._money(order.total_payments),
                    "balance_due_before_receipt": balance_before,
                    "current_allocation": current_allocation,
                    "resulting_balance_due": BankReceiptService._money(
                        max(0.0, balance_before - current_allocation)
                    ),
                }
            )

        allocated_amount = BankReceiptService._money(sum(payment.amount for payment in payments))
        receipt_amount = BankReceiptService._money(receipt.amount)
        return {
            "receipt_id": int(receipt.id or 0),
            "status": receipt.status,
            "currency": receipt.currency,
            "receipt_amount": receipt_amount,
            "allocated_amount": allocated_amount,
            "unallocated_amount": BankReceiptService._money(max(0.0, receipt_amount - allocated_amount)),
            "orders": items,
        }

    @staticmethod
    async def replace(
        session: AsyncSession,
        *,
        receipt_id: int,
        allocations: list[dict[str, Any]],
        payment_type: str = "postpayment",
        metadata_updates: Optional[dict[str, Any]] = None,
    ) -> BankReceipt:
        receipt_result = await session.execute(
            select(BankReceipt).where(BankReceipt.id == receipt_id).with_for_update()
        )
        receipt = receipt_result.scalar_one_or_none()
        if not receipt:
            raise ValueError("Bank receipt not found")
        if receipt.amount <= 0:
            raise ValueError("Bank receipt amount is not valid")
        if receipt.status in {"void", "closed_orders", "non_order_income", "parse_failed"}:
            raise ValueError("Bank receipt cannot be allocated in its current status")

        try:
            normalized_payment_type = PaymentType(payment_type)
        except ValueError as exc:
            raise ValueError(f"Invalid payment type: {payment_type}") from exc

        normalized_allocations: list[dict[str, Any]] = []
        seen_order_ids: set[int] = set()
        for item in allocations:
            order_id = int(item.get("order_id") or 0)
            amount = BankReceiptService._money(item.get("amount"))
            if not order_id or amount <= BankReceiptService.EXACT_AMOUNT_TOLERANCE:
                raise ValueError("Each allocation requires an order and a positive amount")
            if order_id in seen_order_ids:
                raise ValueError(f"Order #{order_id} is listed more than once")
            seen_order_ids.add(order_id)
            normalized_allocations.append({"order_id": order_id, "amount": amount})

        allocated_amount = BankReceiptService._money(sum(item["amount"] for item in normalized_allocations))
        receipt_amount = BankReceiptService._money(receipt.amount)
        if allocated_amount - receipt_amount > BankReceiptService.EXACT_AMOUNT_TOLERANCE:
            raise ValueError("Allocated amount cannot exceed bank receipt amount")

        existing_result = await session.execute(
            select(Payment).where(Payment.bank_receipt_id == receipt.id).order_by(Payment.id.asc())
        )
        existing_payments = list(existing_result.scalars().all())
        existing_by_order: dict[int, float] = {}
        for payment in existing_payments:
            order_id = int(payment.order_id)
            existing_by_order[order_id] = BankReceiptService._money(
                existing_by_order.get(order_id, 0) + payment.amount
            )
        existing_order_ids = set(existing_by_order)

        if normalized_allocations:
            orders = await BankReceiptService._load_receipt_candidate_orders(
                session,
                receipt,
                order_ids=[item["order_id"] for item in normalized_allocations],
                allow_closed_order_ids=existing_order_ids,
            )
        else:
            orders = []

        expected_unp = BankReceiptService._normalize_unp(receipt.payer_unp)
        if not expected_unp:
            raise ValueError("Bank receipt payer UNP is required for payment allocation")
        orders_by_id = {int(order.id or 0): order for order in orders}
        for item in normalized_allocations:
            order = orders_by_id[item["order_id"]]
            order_unp = BankReceiptService._normalize_unp(order.customer.inn if order.customer else "")
            if order_unp != expected_unp:
                raise ValueError("Selected orders do not belong to the bank receipt payer UNP")
            current_allocation = existing_by_order.get(item["order_id"], 0.0)
            other_payments = BankReceiptService._money(float(order.total_payments or 0) - current_allocation)
            balance_before = BankReceiptService._money(max(0.0, float(order.total_amount or 0) - other_payments))
            if item["amount"] - balance_before > BankReceiptService.EXACT_AMOUNT_TOLERANCE:
                raise ValueError(
                    f"Allocation for order #{item['order_id']} exceeds its debt "
                    f"({item['amount']} > {balance_before})"
                )

        existing_signature = sorted(
            (int(payment.order_id), BankReceiptService._money(payment.amount), payment.type)
            for payment in existing_payments
        )
        requested_signature = sorted(
            (item["order_id"], item["amount"], normalized_payment_type)
            for item in normalized_allocations
        )
        if existing_signature == requested_signature:
            return receipt

        affected_order_ids = existing_order_ids | seen_order_ids
        previous_payment_ids = [int(payment.id or 0) for payment in existing_payments if payment.id]
        for payment in existing_payments:
            await session.delete(payment)
        await session.flush()

        new_payments: list[Payment] = []
        for item in normalized_allocations:
            payment = Payment(
                order_id=item["order_id"],
                bank_receipt_id=receipt.id,
                amount=item["amount"],
                currency=receipt.currency,
                date=receipt.received_at,
                type=normalized_payment_type,
                comment=f"Распределено из банковского поступления #{receipt.id}",
            )
            session.add(payment)
            new_payments.append(payment)
        await session.flush()

        for order_id in affected_order_ids:
            order = orders_by_id.get(order_id) or await session.get(Order, order_id)
            if not order:
                continue
            await OrderService._refresh_order_financials(session, order)
            session.add(order)

        payment_items = [
            {
                "payment_id": int(payment.id or 0),
                "order_id": int(payment.order_id),
                "amount": BankReceiptService._money(payment.amount),
            }
            for payment in new_payments
        ]
        unallocated_amount = BankReceiptService._money(max(0.0, receipt_amount - allocated_amount))
        meta = dict(receipt.match_meta or {})
        meta.update(
            {
                "manual_allocations": True,
                "previous_group_payment_ids": previous_payment_ids or None,
                "group_order_ids": [item["order_id"] for item in payment_items],
                "group_payment_ids": [item["payment_id"] for item in payment_items],
                "group_payments": payment_items,
                "group_total": allocated_amount,
                "allocated_amount": allocated_amount,
                "unallocated_amount": unallocated_amount,
            }
        )
        meta.update(metadata_updates or {})
        if not payment_items:
            receipt.status = "requires_review"
            receipt.matched_order_id = None
            receipt.matched_payment_id = None
        else:
            receipt.status = (
                "matched"
                if unallocated_amount <= BankReceiptService.EXACT_AMOUNT_TOLERANCE
                else "partially_allocated"
            )
            receipt.matched_order_id = payment_items[0]["order_id"]
            receipt.matched_payment_id = payment_items[0]["payment_id"]
        receipt.match_meta = meta
        session.add(receipt)
        await session.commit()
        await session.refresh(receipt)
        return receipt
