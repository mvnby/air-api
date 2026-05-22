import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import BankReceipt, PaymentCurrency
from services.bank_receipt_service import BankReceiptService


@dataclass(frozen=True)
class ParsedBankStatementCredit:
    bank_code: str
    payer_account: Optional[str]
    payment_document_number: Optional[str]
    amount: float
    currency: PaymentCurrency
    operation_date: datetime
    payment_purpose: str
    payer_name: str
    payer_unp: Optional[str]

    @property
    def reconciliation_key(self) -> str:
        return BankStatementCsvService.build_reconciliation_key(
            received_at=self.operation_date,
            amount=self.amount,
            payer_unp=self.payer_unp,
            payment_document_number=self.payment_document_number,
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
    HEADER_MARKER = "Код банка"

    @staticmethod
    def _decode_csv(content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("cp1251", errors="replace")

    @staticmethod
    def _clean_excel_text(value: str | None) -> str:
        text = str(value or "").strip()
        if text.startswith('="') and text.endswith('"'):
            text = text[2:-1]
        return text.strip()

    @staticmethod
    def _parse_amount(value: str | None) -> Optional[float]:
        text = BankStatementCsvService._clean_excel_text(value).replace(" ", "").replace(",", ".")
        if not text:
            return None
        try:
            return float(Decimal(text))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _parse_date(value: str | None) -> datetime:
        return datetime.combine(datetime.strptime(str(value or "").strip(), "%d.%m.%Y").date(), time.min)

    @staticmethod
    def _normalize_document_number(value: str | None) -> Optional[str]:
        text = BankStatementCsvService._clean_excel_text(value)
        return text or None

    @staticmethod
    def _normalize_purpose(value: str | None) -> str:
        text = BankStatementCsvService._clean_excel_text(value)
        text = re.sub(r"^\s*OTHR\s+\d+\s*,\s*", "", text, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def build_reconciliation_key(
        *,
        received_at: Optional[datetime],
        amount: float,
        payer_unp: Optional[str],
        payment_document_number: Optional[str],
    ) -> str:
        date_part = received_at.date().isoformat() if received_at else ""
        amount_part = str(int(round(float(amount or 0) * 100)))
        unp_part = str(payer_unp or "").strip()
        doc_part = str(payment_document_number or "").strip().lstrip("0") or str(payment_document_number or "").strip()
        return "|".join([date_part, amount_part, unp_part, doc_part])

    @staticmethod
    def _fingerprint(credit: ParsedBankStatementCredit) -> str:
        raw = "|".join(
            [
                "statement",
                credit.reconciliation_key,
                credit.payer_account or "",
                BankStatementCsvService._normalize_purpose(credit.payment_purpose).casefold(),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def parse(content: bytes) -> list[ParsedBankStatementCredit]:
        text = BankStatementCsvService._decode_csv(content)
        rows = list(csv.reader(StringIO(text), delimiter=";"))
        header_index = next((index for index, row in enumerate(rows) if row and row[0] == BankStatementCsvService.HEADER_MARKER), None)
        if header_index is None:
            raise ValueError("Bank statement CSV header not found")

        header = rows[header_index]
        indexes = {name: idx for idx, name in enumerate(header) if name}
        required = ["Код банка", "Счет-корреспондент", "Номер документа", "Обороты: кредит", "Дата операции", "Назначение", "Наименование контрагента", "УНП контрагента"]
        missing = [name for name in required if name not in indexes]
        if missing:
            raise ValueError(f"Bank statement CSV missing columns: {', '.join(missing)}")

        credits: list[ParsedBankStatementCredit] = []
        for row in rows[header_index + 1 :]:
            if not row or row[0].startswith("Итого"):
                continue
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            amount = BankStatementCsvService._parse_amount(row[indexes["Обороты: кредит"]])
            if not amount or amount <= 0:
                continue
            purpose = BankStatementCsvService._normalize_purpose(row[indexes["Назначение"]])
            credits.append(
                ParsedBankStatementCredit(
                    bank_code=BankStatementCsvService._clean_excel_text(row[indexes["Код банка"]]),
                    payer_account=BankStatementCsvService._clean_excel_text(row[indexes["Счет-корреспондент"]]) or None,
                    payment_document_number=BankStatementCsvService._normalize_document_number(row[indexes["Номер документа"]]),
                    amount=amount,
                    currency=PaymentCurrency.BYN,
                    operation_date=BankStatementCsvService._parse_date(row[indexes["Дата операции"]]),
                    payment_purpose=purpose,
                    payer_name=BankStatementCsvService._clean_excel_text(row[indexes["Наименование контрагента"]]),
                    payer_unp=BankStatementCsvService._clean_excel_text(row[indexes["УНП контрагента"]]) or None,
                )
            )
        return credits

    @staticmethod
    async def _find_existing_for_credit(session: AsyncSession, credit: ParsedBankStatementCredit) -> list[BankReceipt]:
        doc_number = credit.payment_document_number or ""
        doc_number_no_zero = doc_number.lstrip("0") or doc_number
        stmt = select(BankReceipt).where(
            func.date(BankReceipt.received_at) == credit.operation_date.date(),
            BankReceipt.payer_unp == credit.payer_unp,
            BankReceipt.amount == credit.amount,
        )
        result = await session.execute(stmt)
        receipts = list(result.scalars().all())
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
            match_meta={"source": "bank_statement_csv", "statement_reconciliation_key": credit.reconciliation_key},
        )

    @staticmethod
    async def import_statement(session: AsyncSession, content: bytes) -> BankStatementImportResult:
        credits = BankStatementCsvService.parse(content)
        result = BankStatementImportResult(rows=len(credits), credit_rows=len(credits))
        seen_statement_keys: set[str] = set()

        for credit in credits:
            seen_statement_keys.add(credit.reconciliation_key)
            existing = await BankStatementCsvService._find_existing_for_credit(session, credit)
            if existing:
                primary = existing[0]
                meta = dict(primary.match_meta or {})
                meta["statement_seen"] = True
                meta["statement_reconciliation_key"] = credit.reconciliation_key
                primary.match_meta = meta
                session.add(primary)
                result.matched_existing += 1
                if primary.id:
                    result.receipt_ids.append(int(primary.id))
                    result.matched_receipt_ids.append(int(primary.id))
                for duplicate in existing[1:]:
                    duplicate_meta = dict(duplicate.match_meta or {})
                    duplicate_meta["statement_duplicate_candidate"] = True
                    duplicate_meta["statement_reconciliation_key"] = credit.reconciliation_key
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
                BankReceipt.status != "void",
            )
            existing_result = await session.execute(existing_stmt)
            for receipt in existing_result.scalars().all():
                key = BankStatementCsvService.build_reconciliation_key(
                    received_at=receipt.received_at,
                    amount=receipt.amount,
                    payer_unp=receipt.payer_unp,
                    payment_document_number=receipt.payment_document_number,
                )
                if key not in seen_statement_keys:
                    meta = dict(receipt.match_meta or {})
                    meta["missing_in_last_statement"] = True
                    meta["last_statement_period"] = {"from": start_date.isoformat(), "to": end_date.isoformat()}
                    receipt.match_meta = meta
                    session.add(receipt)
                    result.suspicious += 1
                    if receipt.id:
                        result.suspicious_receipt_ids.append(int(receipt.id))

        await session.commit()
        return result
