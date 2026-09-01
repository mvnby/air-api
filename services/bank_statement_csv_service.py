import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import BankReceipt
from services.bank_receipt_service import BankReceiptService
from services.bank_statement_csv_parser import (
    BELGAZPROMBANK_STATEMENT_FORMAT,
    ParsedBankStatement,
    ParsedBankStatementCredit,
    build_statement_reconciliation_key,
    normalize_statement_purpose,
    parse_bank_statement_csv,
)


@dataclass
class BankStatementImportResult:
    rows: int = 0
    credit_rows: int = 0
    created: int = 0
    matched_existing: int = 0
    skipped: int = 0
    suspicious: int = 0
    receipt_ids: list[int] = field(default_factory=list)
    created_receipt_ids: list[int] = field(default_factory=list)
    matched_receipt_ids: list[int] = field(default_factory=list)
    suspicious_receipt_ids: list[int] = field(default_factory=list)


class BankStatementCsvService:
    SOURCE_SCOPED_FORMATS = frozenset({BELGAZPROMBANK_STATEMENT_FORMAT})

    @staticmethod
    def build_reconciliation_key(
        *,
        received_at: Optional[datetime],
        amount: float,
        payer_unp: Optional[str],
        payment_document_number: Optional[str],
    ) -> str:
        return build_statement_reconciliation_key(
            received_at=received_at,
            amount=amount,
            payer_unp=payer_unp,
            payment_document_number=payment_document_number,
        )

    @staticmethod
    def _fingerprint(credit: ParsedBankStatementCredit) -> str:
        raw = "|".join(
            [
                "statement",
                credit.statement_format,
                credit.reconciliation_key,
                credit.payer_account or "",
                normalize_statement_purpose(credit.payment_purpose).casefold(),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def parse(content: bytes) -> list[ParsedBankStatementCredit]:
        return list(BankStatementCsvService.parse_statement(content).credits)

    @staticmethod
    def parse_statement(content: bytes) -> ParsedBankStatement:
        return parse_bank_statement_csv(content)

    @staticmethod
    def _receipt_is_in_statement_scope(
        receipt: BankReceipt,
        *,
        statement_format: str,
    ) -> bool:
        if statement_format not in BankStatementCsvService.SOURCE_SCOPED_FORMATS:
            return True
        return (receipt.match_meta or {}).get("statement_format") == statement_format

    @staticmethod
    async def _find_existing_for_credit(
        session: AsyncSession, credit: ParsedBankStatementCredit
    ) -> list[BankReceipt]:
        doc_number = credit.payment_document_number or ""
        doc_number_no_zero = doc_number.lstrip("0") or doc_number
        stmt = select(BankReceipt).where(
            func.date(BankReceipt.received_at) == credit.operation_date.date(),
            BankReceipt.payer_unp == credit.payer_unp,
            BankReceipt.amount == credit.amount,
        )
        result = await session.execute(stmt)
        receipts = [
            receipt
            for receipt in result.scalars().all()
            if BankStatementCsvService._receipt_is_in_statement_scope(
                receipt,
                statement_format=credit.statement_format,
            )
        ]
        if not doc_number:
            return receipts
        return [
            receipt
            for receipt in receipts
            if not receipt.payment_document_number
            or receipt.payment_document_number == doc_number
            or receipt.payment_document_number.lstrip("0") == doc_number_no_zero
        ]

    @staticmethod
    def _receipt_from_credit(credit: ParsedBankStatementCredit) -> BankReceipt:
        fingerprint = BankStatementCsvService._fingerprint(credit)
        return BankReceipt(
            status="new",
            operation_type="incoming_funds",
            sender_email="bank-statement@local",
            subject="Bank statement CSV import",
            message_id=None,
            fingerprint=fingerprint,
            received_at=credit.operation_date,
            amount=credit.amount,
            currency=credit.currency,
            payer_name=credit.payer_name,
            payer_unp=credit.payer_unp,
            payer_account=credit.payer_account,
            payment_document_raw=credit.payment_document_number,
            payment_document_number=credit.payment_document_number,
            payment_purpose=credit.payment_purpose,
            raw_body=(
                f"CSV statement row: {credit.operation_date.date().isoformat()} "
                f"{credit.amount:g} {credit.currency.value} {credit.payer_name} УНП {credit.payer_unp or '-'}"
            ),
            match_meta={
                "source": "bank_statement_csv",
                "statement_format": credit.statement_format,
                "statement_reconciliation_key": credit.reconciliation_key,
            },
        )

    @staticmethod
    async def import_statement(
        session: AsyncSession, content: bytes
    ) -> BankStatementImportResult:
        statement = BankStatementCsvService.parse_statement(content)
        credits = statement.credits
        result = BankStatementImportResult(
            rows=statement.rows,
            credit_rows=len(credits),
            skipped=statement.skipped,
        )
        seen_statement_keys: set[str] = set()

        for credit in credits:
            seen_statement_keys.add(credit.reconciliation_key)
            existing = await BankStatementCsvService._find_existing_for_credit(
                session, credit
            )
            if existing:
                primary = existing[0]
                meta = dict(primary.match_meta or {})
                meta["statement_seen"] = True
                meta["statement_format"] = credit.statement_format
                meta["statement_reconciliation_key"] = credit.reconciliation_key
                meta.pop("missing_in_last_statement", None)
                meta.pop("last_statement_period", None)
                primary.match_meta = meta
                session.add(primary)
                result.matched_existing += 1
                if primary.id:
                    result.receipt_ids.append(int(primary.id))
                    result.matched_receipt_ids.append(int(primary.id))
                for duplicate in existing[1:]:
                    duplicate_meta = dict(duplicate.match_meta or {})
                    duplicate_meta["statement_duplicate_candidate"] = True
                    duplicate_meta["statement_reconciliation_key"] = (
                        credit.reconciliation_key
                    )
                    duplicate.match_meta = duplicate_meta
                    session.add(duplicate)
                    result.suspicious += 1
                    if duplicate.id:
                        result.suspicious_receipt_ids.append(int(duplicate.id))
                continue

            receipt = BankStatementCsvService._receipt_from_credit(credit)
            session.add(receipt)
            await session.flush()
            await BankReceiptService.match_receipt(session, receipt)
            result.created += 1
            if receipt.id:
                result.receipt_ids.append(int(receipt.id))
                result.created_receipt_ids.append(int(receipt.id))

        if credits:
            start_date = min(item.operation_date.date() for item in credits)
            end_date = max(item.operation_date.date() for item in credits)
            existing_stmt = select(BankReceipt).where(
                BankReceipt.operation_type == "incoming_funds",
                BankReceipt.amount > 0,
                func.date(BankReceipt.received_at) >= start_date,
                func.date(BankReceipt.received_at) <= end_date,
                BankReceipt.status.notin_(
                    ["void", "closed_orders", "non_order_income"]
                ),
            )
            existing_result = await session.execute(existing_stmt)
            for receipt in existing_result.scalars().all():
                if not BankStatementCsvService._receipt_is_in_statement_scope(
                    receipt,
                    statement_format=statement.statement_format,
                ):
                    continue
                key = BankStatementCsvService.build_reconciliation_key(
                    received_at=receipt.received_at,
                    amount=receipt.amount,
                    payer_unp=receipt.payer_unp,
                    payment_document_number=receipt.payment_document_number,
                )
                if key not in seen_statement_keys:
                    meta = dict(receipt.match_meta or {})
                    meta["missing_in_last_statement"] = True
                    meta["last_statement_period"] = {
                        "from": start_date.isoformat(),
                        "to": end_date.isoformat(),
                    }
                    receipt.match_meta = meta
                    session.add(receipt)
                    result.suspicious += 1
                    if receipt.id:
                        result.suspicious_receipt_ids.append(int(receipt.id))

        await session.commit()
        return result
