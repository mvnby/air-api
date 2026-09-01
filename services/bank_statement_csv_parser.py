import csv
import re
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Optional

from models import PaymentCurrency


BELAGROPROMBANK_STATEMENT_FORMAT = "belagroprombank"
BELGAZPROMBANK_STATEMENT_FORMAT = "belgazprombank"


@dataclass(frozen=True)
class ParsedBankStatementCredit:
    statement_format: str
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
        return build_statement_reconciliation_key(
            received_at=self.operation_date,
            amount=self.amount,
            payer_unp=self.payer_unp,
            payment_document_number=self.payment_document_number,
        )


@dataclass(frozen=True)
class ParsedBankStatement:
    statement_format: str
    rows: int
    skipped: int
    credits: tuple[ParsedBankStatementCredit, ...]


@dataclass(frozen=True)
class _StatementProfile:
    name: str
    columns: dict[str, str]
    required_headers: frozenset[str]
    default_currency: Optional[PaymentCurrency] = None
    summary_prefixes: tuple[str, ...] = ()


_BELAGROPROMBANK_COLUMNS = {
    "bank_code": "Код банка",
    "payer_account": "Счет-корреспондент",
    "document_number": "Номер документа",
    "debit": "Обороты: дебет",
    "credit": "Обороты: кредит",
    "operation_date": "Дата операции",
    "purpose": "Назначение",
    "payer_name": "Наименование контрагента",
    "payer_unp": "УНП контрагента",
}

_BELGAZPROMBANK_COLUMNS = {
    "operation_date": "Документ - Дата",
    "document_number": "Документ - №",
    "currency": "Корреспондент - Валюта",
    "bank_code": "Корреспондент - Код",
    "payer_name": "Корреспондент - Название",
    "payer_unp": "Корреспондент - УНП",
    "payer_account": "Корреспондент - Счет",
    "debit": "Номинал - Дебет",
    "credit": "Номинал - Кредит",
    "purpose": "Назначение платежа",
}

_STATEMENT_PROFILES = (
    _StatementProfile(
        name=BELAGROPROMBANK_STATEMENT_FORMAT,
        columns=_BELAGROPROMBANK_COLUMNS,
        required_headers=frozenset(
            {
                "Код банка",
                "Счет-корреспондент",
                "Номер документа",
                "Обороты: кредит",
                "Дата операции",
                "Назначение",
                "Наименование контрагента",
                "УНП контрагента",
            }
        ),
        default_currency=PaymentCurrency.BYN,
        summary_prefixes=("Итого",),
    ),
    _StatementProfile(
        name=BELGAZPROMBANK_STATEMENT_FORMAT,
        columns=_BELGAZPROMBANK_COLUMNS,
        required_headers=frozenset(_BELGAZPROMBANK_COLUMNS.values()),
    ),
)


def decode_bank_statement_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("cp1251", errors="replace")


def clean_statement_text(value: str | None) -> str:
    text = str(value or "").strip()
    if text.startswith('="') and text.endswith('"'):
        text = text[2:-1]
    return text.strip()


def normalize_statement_purpose(value: str | None) -> str:
    text = clean_statement_text(value)
    text = re.sub(r"^\s*OTHR\s+\d+\s*,\s*", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def build_statement_reconciliation_key(
    *,
    received_at: Optional[datetime],
    amount: float,
    payer_unp: Optional[str],
    payment_document_number: Optional[str],
) -> str:
    date_part = received_at.date().isoformat() if received_at else ""
    amount_part = str(int(round(float(amount or 0) * 100)))
    unp_part = str(payer_unp or "").strip()
    document_number = str(payment_document_number or "").strip()
    document_part = document_number.lstrip("0") or document_number
    return "|".join([date_part, amount_part, unp_part, document_part])


def _parse_amount(
    value: str | None, *, row_number: int, column_name: str
) -> Optional[float]:
    text = (
        clean_statement_text(value)
        .replace("\xa0", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    if not text:
        return None
    try:
        return float(Decimal(text))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"Invalid amount in CSV row {row_number}, column {column_name}"
        ) from exc


def _parse_date(value: str | None, *, row_number: int, column_name: str) -> datetime:
    text = clean_statement_text(value)
    try:
        return datetime.combine(datetime.strptime(text, "%d.%m.%Y").date(), time.min)
    except ValueError as exc:
        raise ValueError(
            f"Invalid date in CSV row {row_number}, column {column_name}"
        ) from exc


def _detect_profile(rows: list[list[str]]) -> tuple[_StatementProfile, int, list[str]]:
    best_match: tuple[int, _StatementProfile, int, list[str]] | None = None
    for header_index, raw_header in enumerate(rows):
        header = [clean_statement_text(value) for value in raw_header]
        header_names = {value for value in header if value}
        for profile in _STATEMENT_PROFILES:
            overlap = len(profile.required_headers.intersection(header_names))
            if profile.required_headers.issubset(header_names):
                return profile, header_index, header
            if best_match is None or overlap > best_match[0]:
                best_match = (overlap, profile, header_index, header)

    if best_match:
        overlap, profile, _, header = best_match
        if overlap >= max(2, len(profile.required_headers) // 2):
            missing = sorted(profile.required_headers.difference(header))
            raise ValueError(
                f"Bank statement CSV format {profile.name} is missing columns: "
                f"{', '.join(missing)}"
            )
    raise ValueError("Unsupported bank statement CSV format")


def _row_value(
    row: list[str],
    indexes: dict[str, int],
    profile: _StatementProfile,
    field_name: str,
) -> str | None:
    column_name = profile.columns.get(field_name)
    if not column_name or column_name not in indexes:
        return None
    return row[indexes[column_name]]


def _parse_currency(
    value: str | None,
    *,
    default: Optional[PaymentCurrency],
    row_number: int,
) -> PaymentCurrency:
    text = clean_statement_text(value).upper()
    if not text and default:
        return default
    try:
        return PaymentCurrency(text)
    except ValueError as exc:
        raise ValueError(
            f"Unsupported currency in CSV row {row_number}: {text or '-'}"
        ) from exc


def parse_bank_statement_csv(content: bytes) -> ParsedBankStatement:
    text = decode_bank_statement_csv(content)
    rows = list(csv.reader(StringIO(text), delimiter=";"))
    profile, header_index, header = _detect_profile(rows)
    indexes = {name: index for index, name in enumerate(header) if name}

    credits: list[ParsedBankStatementCredit] = []
    data_rows = 0
    skipped = 0
    for row_index, raw_row in enumerate(
        rows[header_index + 1 :], start=header_index + 2
    ):
        row = list(raw_row)
        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))
        if not any(clean_statement_text(value) for value in row):
            continue
        first_cell = clean_statement_text(row[0])
        if any(first_cell.startswith(prefix) for prefix in profile.summary_prefixes):
            continue

        data_rows += 1
        debit_column = profile.columns.get("debit", "debit")
        credit_column = profile.columns["credit"]
        debit = _parse_amount(
            _row_value(row, indexes, profile, "debit"),
            row_number=row_index,
            column_name=debit_column,
        )
        credit = _parse_amount(
            _row_value(row, indexes, profile, "credit"),
            row_number=row_index,
            column_name=credit_column,
        )
        if debit and debit > 0 and credit and credit > 0:
            raise ValueError(
                f"CSV row {row_index} contains both debit and credit amounts"
            )
        if not credit or credit <= 0:
            skipped += 1
            continue

        currency = _parse_currency(
            _row_value(row, indexes, profile, "currency"),
            default=profile.default_currency,
            row_number=row_index,
        )
        operation_date_column = profile.columns["operation_date"]
        operation_date = _parse_date(
            _row_value(row, indexes, profile, "operation_date"),
            row_number=row_index,
            column_name=operation_date_column,
        )
        document_number = clean_statement_text(
            _row_value(row, indexes, profile, "document_number")
        )
        payer_unp = clean_statement_text(_row_value(row, indexes, profile, "payer_unp"))
        payer_account = clean_statement_text(
            _row_value(row, indexes, profile, "payer_account")
        )
        credits.append(
            ParsedBankStatementCredit(
                statement_format=profile.name,
                bank_code=clean_statement_text(
                    _row_value(row, indexes, profile, "bank_code")
                ),
                payer_account=payer_account or None,
                payment_document_number=document_number or None,
                amount=credit,
                currency=currency,
                operation_date=operation_date,
                payment_purpose=normalize_statement_purpose(
                    _row_value(row, indexes, profile, "purpose")
                ),
                payer_name=clean_statement_text(
                    _row_value(row, indexes, profile, "payer_name")
                ),
                payer_unp=payer_unp or None,
            )
        )

    return ParsedBankStatement(
        statement_format=profile.name,
        rows=data_rows,
        skipped=skipped,
        credits=tuple(credits),
    )
