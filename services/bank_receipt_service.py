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
            conditions.append(BankReceipt.matched_order_id == order_id)

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
    async def match_receipt(session: AsyncSession, receipt: BankReceipt) -> BankReceipt:
        if receipt.id and receipt.matched_payment_id:
            return receipt
        base_meta = dict(receipt.match_meta or {})
        if not receipt.payer_unp or receipt.amount <= 0:
            receipt.status = "requires_review"
            receipt.match_meta = {**base_meta, "reason": "missing_unp_or_amount", "candidate_order_ids": []}
            session.add(receipt)
            await session.flush()
            return receipt

        stmt = (
            select(Order)
            .join(Customer, Customer.id == Order.customer_id)
            .where(
                Customer.inn == receipt.payer_unp,
                Order.status != OrderStatus.CLOSED,
            )
            .options(
                selectinload(Order.customer),
                selectinload(Order.payments),
                selectinload(Order.proposals),
                selectinload(Order.product_links),
                selectinload(Order.service_links),
                selectinload(Order.installers),
            )
        )
        result = await session.execute(stmt)
        orders = list(result.scalars().all())
        document_candidates = await BankReceiptService.find_document_reference_candidates(session, receipt)
        exact_orders: List[Order] = []
        for order in orders:
            await session.refresh(order, attribute_names=["payments", "proposals", "product_links", "service_links", "installers"])
            order.calculate_totals()
            if order.balance_due > 0 and abs(float(order.balance_due) - float(receipt.amount)) <= BankReceiptService.EXACT_AMOUNT_TOLERANCE:
                exact_orders.append(order)

        candidate_ids = [int(order.id) for order in orders if order.id is not None]
        for candidate in document_candidates:
            candidate_order_id = candidate.get("order_id")
            if candidate_order_id and candidate_order_id not in candidate_ids:
                candidate_ids.append(candidate_order_id)
        exact_ids = [int(order.id) for order in exact_orders if order.id is not None]
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
                "document_candidates": document_candidates,
            }
        else:
            reason = "multi_document_payment" if BankReceiptService._looks_like_multi_document_payment(receipt.payment_purpose) else "not_exactly_one_candidate"
            receipt.status = "requires_review"
            receipt.match_meta = {
                **base_meta,
                "reason": reason,
                "candidate_order_ids": candidate_ids,
                "exact_order_ids": exact_ids,
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
        if normalized_status not in {"requires_review", "matched", "void", "parse_failed"}:
            raise ValueError("Unsupported bank receipt status")
        if normalized_status == "matched":
            raise ValueError("Use attach action to match a bank receipt")

        old_payment_id = receipt.matched_payment_id
        old_order_id = receipt.matched_order_id
        if normalized_status == "void" and old_payment_id:
            payment = await session.get(Payment, old_payment_id)
            if payment and payment.bank_receipt_id == receipt.id:
                await session.delete(payment)
                await session.flush()
                if payment.order_id:
                    order = await session.get(Order, payment.order_id)
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
            }
        )
        receipt.status = normalized_status
        if normalized_status in {"void", "requires_review"}:
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
