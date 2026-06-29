import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import BankReceipt, Customer, Order, OrderDocument, OrderStatus, Payment, PaymentCurrency, PaymentType
from services.bank_email_parser_service import BankEmailParseError, BankEmailParserService, ParsedBankReceipt
from services.order_service import OrderService


@dataclass
class BankReceiptImportResult:
    processed: int = 0
    created: int = 0
    duplicates: int = 0
    failed: int = 0
    receipt_ids: List[int] = field(default_factory=list)
    created_receipt_ids: List[int] = field(default_factory=list)


class BankReceiptService:
    EXACT_AMOUNT_TOLERANCE = 0.01
    RESOLVED_UNMATCHED_STATUSES = {"closed_orders", "non_order_income"}

    @staticmethod
    def _money(value: Any) -> float:
        return round(float(value or 0), 2)

    @staticmethod
    def _money_cents(value: Any) -> int:
        return int(round(BankReceiptService._money(value) * 100))

    @staticmethod
    def _normalize_unp(value: Any) -> str:
        return re.sub(r"\D+", "", str(value or ""))

    @staticmethod
    async def list_receipts(
        session: AsyncSession,
        *,
        page: int = 1,
        limit: int = 50,
        status: Optional[str] = None,
        payer_unp: Optional[str] = None,
        order_id: Optional[int] = None,
    ) -> tuple[List[BankReceipt], int]:
        safe_page = max(1, int(page or 1))
        safe_limit = min(100, max(1, int(limit or 50)))
        conditions = []
        if status:
            conditions.append(BankReceipt.status == status)
        if payer_unp:
            conditions.append(BankReceipt.payer_unp == payer_unp)
        if order_id:
            receipt_ids_for_order = select(Payment.bank_receipt_id).where(
                Payment.order_id == order_id,
                Payment.bank_receipt_id.is_not(None),
            )
            conditions.append(or_(BankReceipt.matched_order_id == order_id, BankReceipt.id.in_(receipt_ids_for_order)))

        count_stmt = select(func.count(BankReceipt.id))
        stmt = select(BankReceipt)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
            stmt = stmt.where(*conditions)
        total = int((await session.execute(count_stmt)).scalar_one() or 0)
        result = await session.execute(
            stmt.order_by(BankReceipt.created_at.desc()).offset((safe_page - 1) * safe_limit).limit(safe_limit)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def process_email(
        session: AsyncSession,
        *,
        sender_email: str,
        subject: str,
        raw_body: str,
        message_id: Optional[str] = None,
        email_date_raw: Optional[str] = None,
    ) -> tuple[BankReceipt, bool]:
        try:
            parsed = BankEmailParserService.parse(
                sender_email=sender_email,
                subject=subject,
                raw_body=raw_body,
                message_id=message_id,
                email_date_raw=email_date_raw,
            )
            existing = await BankReceiptService._find_duplicate(
                session,
                message_id=parsed.message_id,
                fingerprint=parsed.fingerprint,
            )
            if existing:
                return existing, False
            receipt = BankReceiptService._receipt_from_parsed(parsed)
        except BankEmailParseError as exc:
            fingerprint = BankEmailParserService.build_fingerprint(
                sender_email=sender_email,
                subject=subject,
                received_at=None,
                amount=None,
                payer_unp=None,
                payment_document_number=None,
                payment_purpose=None,
                raw_body=raw_body,
            )
            existing = await BankReceiptService._find_duplicate(
                session,
                message_id=(message_id or "").strip() or None,
                fingerprint=fingerprint,
            )
            if existing:
                return existing, False
            receipt = BankReceipt(
                status="parse_failed",
                operation_type="incoming_funds",
                sender_email=str(sender_email or "").strip().lower(),
                subject=str(subject or "").strip(),
                message_id=(message_id or "").strip() or None,
                fingerprint=fingerprint,
                amount=0.0,
                currency=PaymentCurrency.BYN,
                raw_body=str(raw_body or ""),
                parse_error=str(exc),
            )

        session.add(receipt)
        await session.flush()
        if receipt.status != "parse_failed":
            await BankReceiptService.match_receipt(session, receipt)
        await session.commit()
        await session.refresh(receipt)
        return receipt, True

    @staticmethod
    async def _find_duplicate(
        session: AsyncSession,
        *,
        message_id: Optional[str],
        fingerprint: str,
    ) -> Optional[BankReceipt]:
        predicates = [BankReceipt.fingerprint == fingerprint]
        if message_id:
            predicates.append(BankReceipt.message_id == message_id)
        result = await session.execute(select(BankReceipt).where(or_(*predicates)).limit(1))
        return result.scalar_one_or_none()

    @staticmethod
    def _receipt_from_parsed(parsed: ParsedBankReceipt) -> BankReceipt:
        return BankReceipt(
            status="new",
            operation_type=parsed.operation_type,
            sender_email=parsed.sender_email,
            subject=parsed.subject,
            message_id=parsed.message_id,
            fingerprint=parsed.fingerprint,
            email_date=parsed.email_date,
            received_at=parsed.received_at,
            our_account=parsed.our_account,
            amount=parsed.amount,
            currency=parsed.currency,
            payer_name=parsed.payer_name,
            payer_unp=parsed.payer_unp,
            payer_account=parsed.payer_account,
            payment_document_raw=parsed.payment_document_raw,
            payment_document_number=parsed.payment_document_number,
            payment_purpose=parsed.payment_purpose,
            account_balance_after=parsed.account_balance_after,
            raw_body=parsed.raw_body,
        )

    @staticmethod
    def _looks_like_multi_document_payment(purpose: Optional[str]) -> bool:
        text = str(purpose or "").casefold()
        markers = re.findall(r"(?:акт|счет|сч[её]т|договор|кп|n|№)\s*[№n]?\s*\d+", text)
        return len(markers) > 1

    @staticmethod
    def _looks_like_non_order_income(purpose: Optional[str]) -> bool:
        text = " ".join(str(purpose or "").casefold().split())
        if not text:
            return False
        return (
            "выплата процентов" in text
            and "временно свободными средствами" in text
            and "находящимися на счете" in text
        )

    @staticmethod
    def _document_reference_tokens(number: str) -> set[str]:
        raw = str(number or "").strip()
        if not raw:
            return set()
        compact = re.sub(r"\s+", "", raw).casefold()
        tokens = {compact}
        return {token for token in tokens if len(token) >= 3}

    @staticmethod
    async def find_document_reference_candidates(session: AsyncSession, receipt: BankReceipt) -> list[dict[str, Any]]:
        purpose = str(receipt.payment_purpose or "").casefold().replace(" ", "")
        if not purpose:
            return []
        stmt = select(OrderDocument).order_by(OrderDocument.created_at.desc()).limit(500)
        result = await session.execute(stmt)
        candidates: list[dict[str, Any]] = []
        seen_order_ids: set[int] = set()
        for doc in result.scalars().all():
            tokens = BankReceiptService._document_reference_tokens(doc.number)
            if not tokens or not any(token in purpose for token in tokens):
                continue
            if doc.order_id in seen_order_ids:
                continue
            seen_order_ids.add(doc.order_id)
            candidates.append(
                {
                    "order_id": int(doc.order_id),
                    "document_id": int(doc.id or 0),
                    "doc_type": doc.doc_type,
                    "number": doc.number,
                }
            )
        return candidates

    @staticmethod
    async def _load_receipt_candidate_orders(
        session: AsyncSession,
        receipt: BankReceipt,
        *,
        order_ids: Optional[List[int]] = None,
    ) -> list[Order]:
        unique_order_ids = sorted({int(order_id) for order_id in (order_ids or []) if order_id})
        if not unique_order_ids and not receipt.payer_unp:
            return []

        conditions = [Order.status != OrderStatus.CLOSED]
        if unique_order_ids:
            conditions.append(Order.id.in_(unique_order_ids))
        else:
            conditions.append(Customer.inn == receipt.payer_unp)

        stmt = (
            select(Order)
            .join(Customer, Customer.id == Order.customer_id)
            .where(*conditions)
            .options(
                selectinload(Order.customer),
                selectinload(Order.payments),
                selectinload(Order.proposals),
                selectinload(Order.product_links),
                selectinload(Order.service_links),
                selectinload(Order.installers),
            )
            .order_by(Order.created_at.asc(), Order.id.asc())
        )
        result = await session.execute(stmt)
        orders = list(result.scalars().all())
        if unique_order_ids and len({int(order.id or 0) for order in orders}) != len(unique_order_ids):
            raise ValueError("Some group orders were not found or are already closed")

        for order in orders:
            await session.refresh(order, attribute_names=["payments", "proposals", "product_links", "service_links", "installers"])
            order.calculate_totals()
        return orders

    @staticmethod
    def _order_to_group_item(order: Order) -> dict[str, Any]:
        return {
            "order_id": int(order.id or 0),
            "title": order.title,
            "customer_name": order.customer.name if order.customer else None,
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            "total_amount": BankReceiptService._money(order.total_amount),
            "total_payments": BankReceiptService._money(order.total_payments),
            "balance_due": BankReceiptService._money(order.balance_due),
        }

    @staticmethod
    def _find_exact_group_subset(items: list[dict[str, Any]], target_amount: float) -> list[dict[str, Any]]:
        target_cents = BankReceiptService._money_cents(target_amount)
        if target_cents <= 0:
            return []

        # Keep the state bounded: a single payer can have many old open orders,
        # and we only need one exact, reviewable subset for manager confirmation.
        reachable: dict[int, tuple[int, ...]] = {0: ()}
        max_states = 50000
        for index, item in enumerate(items):
            amount_cents = BankReceiptService._money_cents(item.get("balance_due"))
            if amount_cents <= 0 or amount_cents > target_cents:
                continue
            additions: dict[int, tuple[int, ...]] = {}
            for total, indexes in list(reachable.items()):
                next_total = total + amount_cents
                if next_total > target_cents or next_total in reachable or next_total in additions:
                    continue
                next_indexes = (*indexes, index)
                if next_total == target_cents and len(next_indexes) > 1:
                    return [items[item_index] for item_index in next_indexes]
                additions[next_total] = next_indexes
            reachable.update(additions)
            if len(reachable) > max_states:
                break
        return []

    @staticmethod
    def _build_group_match_meta(receipt: BankReceipt, orders: list[Order]) -> dict[str, Any]:
        debt_orders = [order for order in orders if float(order.balance_due or 0) > BankReceiptService.EXACT_AMOUNT_TOLERANCE]
        open_items = [BankReceiptService._order_to_group_item(order) for order in debt_orders if order.id]
        open_balance_due = BankReceiptService._money(sum(item["balance_due"] for item in open_items))
        receipt_amount = BankReceiptService._money(receipt.amount)
        selection_mode = "all_open"
        selected_items = open_items
        is_exact = (
            len(open_items) > 1
            and abs(open_balance_due - receipt_amount) <= BankReceiptService.EXACT_AMOUNT_TOLERANCE
        )
        if not is_exact:
            exact_subset = BankReceiptService._find_exact_group_subset(open_items, receipt_amount)
            if exact_subset:
                selected_items = exact_subset
                selection_mode = "exact_subset"
                is_exact = True
            else:
                selection_mode = "all_open_not_exact"

        selected_balance_due = BankReceiptService._money(sum(item["balance_due"] for item in selected_items))
        return {
            "available": len(selected_items) > 1,
            "is_exact": is_exact,
            "selection_mode": selection_mode,
            "total_balance_due": selected_balance_due,
            "open_balance_due": open_balance_due,
            "receipt_amount": receipt_amount,
            "order_ids": [item["order_id"] for item in selected_items],
            "orders": selected_items,
            "open_order_ids": [item["order_id"] for item in open_items],
            "open_orders": open_items,
        }

    @staticmethod
    async def match_receipt(session: AsyncSession, receipt: BankReceipt) -> BankReceipt:
        if receipt.id and receipt.matched_payment_id:
            return receipt
        base_meta = dict(receipt.match_meta or {})
        if BankReceiptService._looks_like_non_order_income(receipt.payment_purpose):
            receipt.status = "non_order_income"
            receipt.match_meta = {
                **base_meta,
                "reason": "bank_interest_income",
                "candidate_order_ids": [],
                "exact_order_ids": [],
                "document_candidates": [],
            }
            session.add(receipt)
            await session.flush()
            return receipt
        if not receipt.payer_unp or receipt.amount <= 0:
            receipt.status = "requires_review"
            receipt.match_meta = {**base_meta, "reason": "missing_unp_or_amount", "candidate_order_ids": []}
            session.add(receipt)
            await session.flush()
            return receipt

        orders = await BankReceiptService._load_receipt_candidate_orders(session, receipt)
        document_candidates = await BankReceiptService.find_document_reference_candidates(session, receipt)
        exact_orders: List[Order] = []
        for order in orders:
            if order.balance_due > 0 and abs(float(order.balance_due) - float(receipt.amount)) <= BankReceiptService.EXACT_AMOUNT_TOLERANCE:
                exact_orders.append(order)

        candidate_ids = [int(order.id) for order in orders if order.id is not None]
        for candidate in document_candidates:
            candidate_order_id = candidate.get("order_id")
            if candidate_order_id and candidate_order_id not in candidate_ids:
                candidate_ids.append(candidate_order_id)
        exact_ids = [int(order.id) for order in exact_orders if order.id is not None]
        group_match = BankReceiptService._build_group_match_meta(receipt, orders)
        if len(exact_orders) == 1 and not BankReceiptService._looks_like_multi_document_payment(receipt.payment_purpose):
            order = exact_orders[0]
            existing_payment = None
            if receipt.id:
                payment_result = await session.execute(select(Payment).where(Payment.bank_receipt_id == receipt.id).limit(1))
                existing_payment = payment_result.scalar_one_or_none()
            if not existing_payment:
                existing_payment = Payment(
                    order_id=int(order.id),
                    bank_receipt_id=receipt.id,
                    amount=receipt.amount,
                    currency=receipt.currency,
                    date=receipt.received_at,
                    type=PaymentType.POSTPAYMENT,
                    comment=f"Автоматически по банковскому поступлению #{receipt.id}",
                )
                session.add(existing_payment)
                await session.flush()

            await OrderService._refresh_order_financials(session, order)
            order.is_paid = order.balance_due <= BankReceiptService.EXACT_AMOUNT_TOLERANCE
            session.add(order)
            receipt.status = "matched"
            receipt.matched_order_id = int(order.id)
            receipt.matched_payment_id = int(existing_payment.id)
            receipt.match_meta = {
                **base_meta,
                "reason": "exact_unp_and_balance_due",
                "candidate_order_ids": candidate_ids,
                "exact_order_ids": exact_ids,
                "group_match": group_match,
                "document_candidates": document_candidates,
            }
        else:
            if group_match["is_exact"]:
                reason = "group_balance_due_exact"
            elif BankReceiptService._looks_like_multi_document_payment(receipt.payment_purpose):
                reason = "multi_document_payment"
            else:
                reason = "not_exactly_one_candidate"
            receipt.status = "requires_review"
            receipt.match_meta = {
                **base_meta,
                "reason": reason,
                "candidate_order_ids": candidate_ids,
                "exact_order_ids": exact_ids,
                "group_match": group_match,
                "document_candidates": document_candidates,
            }

        session.add(receipt)
        await session.flush()
        return receipt

    @staticmethod
    async def attach_receipt_to_order(
        session: AsyncSession,
        *,
        receipt_id: int,
        order_id: int,
        payment_type: str = "postpayment",
    ) -> BankReceipt:
        receipt = await session.get(BankReceipt, receipt_id)
        if not receipt:
            raise ValueError("Bank receipt not found")
        if receipt.status == "matched" or receipt.matched_payment_id:
            raise ValueError("Bank receipt is already attached")
        if receipt.amount <= 0:
            raise ValueError("Bank receipt amount is not valid")

        order = await session.get(Order, order_id)
        if not order:
            raise ValueError("Order not found")

        try:
            ptype = PaymentType(payment_type)
        except ValueError as exc:
            raise ValueError(f"Invalid payment type: {payment_type}") from exc

        payment = Payment(
            order_id=order_id,
            bank_receipt_id=receipt.id,
            amount=receipt.amount,
            currency=receipt.currency,
            date=receipt.received_at,
            type=ptype,
            comment=f"Разнесено вручную по банковскому поступлению #{receipt.id}",
        )
        session.add(payment)
        await session.flush()

        await OrderService._refresh_order_financials(session, order)
        order.is_paid = order.balance_due <= BankReceiptService.EXACT_AMOUNT_TOLERANCE
        session.add(order)

        meta = dict(receipt.match_meta or {})
        meta["manual_attached"] = True
        receipt.status = "matched"
        receipt.matched_order_id = order_id
        receipt.matched_payment_id = int(payment.id)
        receipt.match_meta = meta
        session.add(receipt)
        await session.commit()
        await session.refresh(receipt)
        return receipt

    @staticmethod
    async def attach_receipt_to_order_group(
        session: AsyncSession,
        *,
        receipt_id: int,
        order_ids: Optional[List[int]] = None,
        payment_type: str = "postpayment",
    ) -> BankReceipt:
        receipt = await session.get(BankReceipt, receipt_id)
        if not receipt:
            raise ValueError("Bank receipt not found")
        if receipt.amount <= 0:
            raise ValueError("Bank receipt amount is not valid")

        existing_payment_result = await session.execute(select(Payment).where(Payment.bank_receipt_id == receipt.id).limit(1))
        if receipt.status == "matched" or receipt.matched_payment_id or existing_payment_result.scalar_one_or_none():
            raise ValueError("Bank receipt is already attached")

        try:
            ptype = PaymentType(payment_type)
        except ValueError as exc:
            raise ValueError(f"Invalid payment type: {payment_type}") from exc

        requested_order_ids = [int(order_id) for order_id in (order_ids or []) if order_id]
        if not requested_order_ids:
            requested_order_ids = list((receipt.match_meta or {}).get("group_match", {}).get("order_ids") or [])
        if len(set(requested_order_ids)) < 2:
            raise ValueError("Select at least two unpaid orders for group payment")

        orders = await BankReceiptService._load_receipt_candidate_orders(session, receipt, order_ids=requested_order_ids)
        expected_unp = BankReceiptService._normalize_unp(receipt.payer_unp)
        if not expected_unp:
            raise ValueError("Bank receipt payer UNP is required for group payment")
        foreign_orders = [
            int(order.id or 0)
            for order in orders
            if BankReceiptService._normalize_unp(order.customer.inn if order.customer else "") != expected_unp
        ]
        if foreign_orders:
            raise ValueError("Selected orders do not belong to the bank receipt payer UNP")

        debt_orders = [order for order in orders if float(order.balance_due or 0) > BankReceiptService.EXACT_AMOUNT_TOLERANCE]
        if len(debt_orders) < 2:
            raise ValueError("Group payment requires at least two orders with unpaid balance")

        total_balance_due = BankReceiptService._money(sum(float(order.balance_due or 0) for order in debt_orders))
        receipt_amount = BankReceiptService._money(receipt.amount)
        if abs(total_balance_due - receipt_amount) > BankReceiptService.EXACT_AMOUNT_TOLERANCE:
            raise ValueError(f"Receipt amount {receipt_amount} does not match group debt {total_balance_due}")

        payments: list[Payment] = []
        allocated = 0.0
        for index, order in enumerate(debt_orders):
            if index == len(debt_orders) - 1:
                amount = BankReceiptService._money(receipt_amount - allocated)
            else:
                amount = BankReceiptService._money(order.balance_due)
                allocated = BankReceiptService._money(allocated + amount)
            if amount <= BankReceiptService.EXACT_AMOUNT_TOLERANCE:
                continue
            payment = Payment(
                order_id=int(order.id),
                bank_receipt_id=receipt.id,
                amount=amount,
                currency=receipt.currency,
                date=receipt.received_at,
                type=ptype,
                comment=f"Разнесено по группе заказов из банковского поступления #{receipt.id}",
            )
            session.add(payment)
            payments.append(payment)

        await session.flush()

        for order in debt_orders:
            await OrderService._refresh_order_financials(session, order)
            session.add(order)

        payment_items = [
            {
                "payment_id": int(payment.id or 0),
                "order_id": int(payment.order_id),
                "amount": BankReceiptService._money(payment.amount),
            }
            for payment in payments
        ]
        meta = dict(receipt.match_meta or {})
        meta.update(
            {
                "manual_group_attached": True,
                "group_order_ids": [item["order_id"] for item in payment_items],
                "group_payment_ids": [item["payment_id"] for item in payment_items],
                "group_payments": payment_items,
                "group_total": receipt_amount,
            }
        )
        receipt.status = "matched"
        receipt.matched_order_id = payment_items[0]["order_id"]
        receipt.matched_payment_id = payment_items[0]["payment_id"]
        receipt.match_meta = meta
        session.add(receipt)
        await session.commit()
        await session.refresh(receipt)
        return receipt

    @staticmethod
    async def update_receipt_status(
        session: AsyncSession,
        *,
        receipt_id: int,
        status: str,
        reason: Optional[str] = None,
    ) -> BankReceipt:
        receipt = await session.get(BankReceipt, receipt_id)
        if not receipt:
            raise ValueError("Bank receipt not found")

        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"requires_review", "matched", "void", "parse_failed", "closed_orders", "non_order_income"}:
            raise ValueError("Unsupported bank receipt status")
        if normalized_status == "matched":
            raise ValueError("Use attach action to match a bank receipt")

        old_payment_id = receipt.matched_payment_id
        old_order_id = receipt.matched_order_id
        deleted_payment_ids: list[int] = []
        if normalized_status in {"void", "requires_review", *BankReceiptService.RESOLVED_UNMATCHED_STATUSES}:
            payments_result = await session.execute(select(Payment).where(Payment.bank_receipt_id == receipt.id))
            payments = list(payments_result.scalars().all())
            if not payments and old_payment_id:
                payment = await session.get(Payment, old_payment_id)
                payments = [payment] if payment and payment.bank_receipt_id == receipt.id else []
            affected_order_ids = {int(payment.order_id) for payment in payments if payment and payment.order_id}
            for payment in payments:
                if not payment:
                    continue
                deleted_payment_ids.append(int(payment.id or 0))
                await session.delete(payment)
            await session.flush()
            for order_id in affected_order_ids:
                order = await session.get(Order, order_id)
                if order:
                    await OrderService._refresh_order_financials(session, order)
                    order.is_paid = order.balance_due <= BankReceiptService.EXACT_AMOUNT_TOLERANCE
                    session.add(order)

        meta = dict(receipt.match_meta or {})
        meta.update(
            {
                "manual_status": normalized_status,
                "manual_reason": str(reason or "").strip() or None,
                "previous_status": receipt.status,
                "previous_matched_order_id": old_order_id,
                "previous_matched_payment_id": old_payment_id,
                "previous_matched_payment_ids": deleted_payment_ids or None,
            }
        )
        receipt.status = normalized_status
        if normalized_status in {"void", "requires_review", *BankReceiptService.RESOLVED_UNMATCHED_STATUSES}:
            receipt.matched_order_id = None
            receipt.matched_payment_id = None
        receipt.match_meta = meta
        session.add(receipt)
        await session.commit()
        await session.refresh(receipt)
        return receipt

    @staticmethod
    async def delete_receipt(session: AsyncSession, *, receipt_id: int) -> None:
        receipt = await session.get(BankReceipt, receipt_id)
        if not receipt:
            raise ValueError("Bank receipt not found")
        if receipt.matched_payment_id:
            raise ValueError("Cannot delete bank receipt linked to a payment; mark it as erroneous instead")
        await session.delete(receipt)
        await session.commit()
