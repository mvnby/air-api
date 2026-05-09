import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

from models import PaymentCurrency


class BankEmailParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedBankReceipt:
    operation_type: str
    sender_email: str
    subject: str
    message_id: Optional[str]
    email_date: Optional[datetime]
    received_at: datetime
    our_account: str
    amount: float
    currency: PaymentCurrency
    payer_name: str
    payer_unp: str
    payer_account: str
    payment_document_raw: str
    payment_document_number: Optional[str]
    payment_purpose: str
    account_balance_after: Optional[float]
    raw_body: str
    fingerprint: str


class BankEmailParserService:
    BANK_SENDER = "noreply@service.belapb.by"
    SUBJECT_PREFIX = "Поступление средств на счет"

    @staticmethod
    def is_bank_credit_email(sender_email: str, subject: str) -> bool:
        return (
            str(sender_email or "").strip().lower() == BankEmailParserService.BANK_SENDER
            and str(subject or "").strip().startswith(BankEmailParserService.SUBJECT_PREFIX)
        )

    @staticmethod
    def normalize_text(raw: str) -> str:
        text = str(raw or "").replace("\xa0", " ")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def parse_amount(raw: str) -> float:
        cleaned = str(raw or "").replace(" ", "").replace(",", ".")
        return float(cleaned)

    @staticmethod
    def parse_local_datetime(raw: str) -> datetime:
        match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{2,4})\s+(\d{2}):(\d{2})", raw.strip())
        if not match:
            raise BankEmailParseError(f"Unsupported bank datetime: {raw}")
        day, month, year, hour, minute = match.groups()
        full_year = int(year)
        if full_year < 100:
            full_year += 2000
        return datetime(full_year, int(month), int(day), int(hour), int(minute))

    @staticmethod
    def parse_email_date(raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if parsed and parsed.tzinfo is not None:
            return parsed.replace(tzinfo=None)
        return parsed

    @staticmethod
    def build_fingerprint(
        *,
        sender_email: str,
        subject: str,
        received_at: Optional[datetime],
        amount: Optional[float],
        payer_unp: Optional[str],
        payment_document_number: Optional[str],
        payment_purpose: Optional[str],
        raw_body: str = "",
    ) -> str:
        parts = [
            str(sender_email or "").strip().lower(),
            BankEmailParserService.normalize_text(subject).casefold(),
            received_at.isoformat(timespec="minutes") if received_at else "",
            f"{amount:.2f}" if amount is not None else "",
            str(payer_unp or "").strip(),
            str(payment_document_number or "").strip(),
            BankEmailParserService.normalize_text(payment_purpose).casefold(),
        ]
        if not any(parts[2:]):
            parts.append(BankEmailParserService.normalize_text(raw_body).casefold())
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def parse(
        *,
        sender_email: str,
        subject: str,
        raw_body: str,
        message_id: Optional[str] = None,
        email_date_raw: Optional[str] = None,
    ) -> ParsedBankReceipt:
        if not BankEmailParserService.is_bank_credit_email(sender_email, subject):
            raise BankEmailParseError("Email is not a supported bank credit notification")

        text = BankEmailParserService.normalize_text(raw_body)
        main = re.search(
            r"банковский счет №(?P<our_account>[A-Z0-9]+)\s+"
            r"(?P<received_at>\d{2}\.\d{2}\.\d{2,4}\s+\d{2}:\d{2})\s+"
            r"поступили денежные средства в размере\s+"
            r"(?P<amount>[\d\s]+(?:[.,]\d+)?)\s+"
            r"(?P<currency>[A-ZА-Я]{3})\s+от\s+"
            r"(?P<payer_name>.+?),\s+УНП\s+(?P<payer_unp>\d+)\s+"
            r"со счета №(?P<payer_account>[A-Z0-9]+)\.",
            text,
            re.IGNORECASE,
        )
        if not main:
            raise BankEmailParseError("Could not parse bank receipt header")

        details = re.search(
            r"Реквизиты платежного документа:\s+(?P<doc_raw>.+?),\s+назначение:\s+"
            r"(?P<purpose>.+?)\.\s+Остаток по счету после зачисления составляет\s+"
            r"(?P<balance>[\d\s]+(?:[.,]\d+)?)\s+(?P<balance_currency>[A-ZА-Я]{3})\.",
            text,
            re.IGNORECASE,
        )
        if not details:
            raise BankEmailParseError("Could not parse bank receipt payment details")

        currency_raw = main.group("currency").upper()
        try:
            currency = PaymentCurrency(currency_raw)
        except ValueError as exc:
            raise BankEmailParseError(f"Unsupported bank receipt currency: {currency_raw}") from exc

        doc_raw = BankEmailParserService.normalize_text(details.group("doc_raw"))
        doc_number_match = re.search(r"№\s*([A-Za-zА-Яа-я0-9/-]+)", doc_raw)
        payment_document_number = doc_number_match.group(1) if doc_number_match else None
        received_at = BankEmailParserService.parse_local_datetime(main.group("received_at"))
        amount = BankEmailParserService.parse_amount(main.group("amount"))
        payment_purpose = BankEmailParserService.normalize_text(details.group("purpose"))
        account_balance_after = BankEmailParserService.parse_amount(details.group("balance"))

        fingerprint = BankEmailParserService.build_fingerprint(
            sender_email=sender_email,
            subject=subject,
            received_at=received_at,
            amount=amount,
            payer_unp=main.group("payer_unp"),
            payment_document_number=payment_document_number,
            payment_purpose=payment_purpose,
            raw_body=text,
        )

        return ParsedBankReceipt(
            operation_type="incoming_funds",
            sender_email=str(sender_email or "").strip().lower(),
            subject=str(subject or "").strip(),
            message_id=(message_id or "").strip() or None,
            email_date=BankEmailParserService.parse_email_date(email_date_raw),
            received_at=received_at,
            our_account=main.group("our_account"),
            amount=amount,
            currency=currency,
            payer_name=BankEmailParserService.normalize_text(main.group("payer_name")),
            payer_unp=main.group("payer_unp"),
            payer_account=main.group("payer_account"),
            payment_document_raw=doc_raw,
            payment_document_number=payment_document_number,
            payment_purpose=payment_purpose,
            account_balance_after=account_balance_after,
            raw_body=str(raw_body or ""),
            fingerprint=fingerprint,
        )
