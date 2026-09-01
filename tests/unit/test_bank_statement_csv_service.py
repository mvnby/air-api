import csv
from dataclasses import replace
from io import StringIO

import pytest

from models import BankReceipt, PaymentCurrency
from services.bank_statement_csv_parser import (
    BELAGROPROMBANK_STATEMENT_FORMAT,
    BELGAZPROMBANK_STATEMENT_FORMAT,
)
from services.bank_statement_csv_service import BankStatementCsvService


BELGAZPROMBANK_HEADERS = (
    "Документ - Дата",
    "Документ - №",
    "Документ - Код опер.",
    "Корреспондент - Валюта",
    "Корреспондент - Код",
    "Корреспондент - Название",
    "Корреспондент - УНП",
    "Корреспондент - Счет",
    "Номинал - Дебет",
    "Номинал - Кредит",
    "СМП дата док.",
    "Назначение платежа",
)


def _belgazprombank_csv(*rows: list[str], headers=BELGAZPROMBANK_HEADERS) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _belgazprombank_row(
    *,
    document_number: str = '="000042"',
    currency: str = "BYN",
    debit: str = "",
    credit: str = "1460.00",
    purpose: str = "Оплата по счету 42; без НДС",
) -> list[str]:
    return [
        "01.09.2026",
        document_number,
        "01",
        currency,
        "TESTBY2X",
        'ООО "Тестовый покупатель"',
        "100000002",
        '="BY00TEST00000000000000000000"',
        debit,
        credit,
        "",
        purpose,
    ]


def test_belgazprombank_parser_reads_only_credit_rows_from_utf8_bom_csv():
    content = _belgazprombank_csv(
        _belgazprombank_row(
            document_number="000041",
            debit="125.50",
            credit="",
            purpose="Банковская комиссия",
        ),
        _belgazprombank_row(),
    )

    statement = BankStatementCsvService.parse_statement(content)

    assert statement.statement_format == BELGAZPROMBANK_STATEMENT_FORMAT
    assert statement.rows == 2
    assert statement.skipped == 1
    assert len(statement.credits) == 1
    credit = statement.credits[0]
    assert credit.amount == 1460
    assert credit.currency == PaymentCurrency.BYN
    assert credit.operation_date.isoformat() == "2026-09-01T00:00:00"
    assert credit.bank_code == "TESTBY2X"
    assert credit.payer_name == 'ООО "Тестовый покупатель"'
    assert credit.payer_unp == "100000002"
    assert credit.payer_account == "BY00TEST00000000000000000000"
    assert credit.payment_document_number == "000042"
    assert credit.payment_purpose == "Оплата по счету 42; без НДС"


def test_belgazprombank_parser_rejects_row_with_debit_and_credit():
    content = _belgazprombank_csv(_belgazprombank_row(debit="10.00", credit="20.00"))

    with pytest.raises(ValueError, match="both debit and credit"):
        BankStatementCsvService.parse_statement(content)


def test_belgazprombank_parser_rejects_unsupported_currency():
    content = _belgazprombank_csv(_belgazprombank_row(currency="RUB"))

    with pytest.raises(ValueError, match="Unsupported currency"):
        BankStatementCsvService.parse_statement(content)


def test_belgazprombank_parser_reports_missing_required_column():
    headers = tuple(
        header for header in BELGAZPROMBANK_HEADERS if header != "Номинал - Кредит"
    )
    content = _belgazprombank_csv(headers=headers)

    with pytest.raises(ValueError, match="Номинал - Кредит"):
        BankStatementCsvService.parse_statement(content)


def test_belgazprombank_reconciliation_is_scoped_by_statement_format():
    primary_account_receipt = BankReceipt(
        sender_email="bank@example.test",
        subject="Primary account receipt",
        fingerprint="primary-account-receipt",
        raw_body="synthetic",
    )
    belagaz_receipt = BankReceipt(
        sender_email="bank-statement@local",
        subject="Belgazprombank statement receipt",
        fingerprint="belgazprombank-receipt",
        raw_body="synthetic",
        match_meta={"statement_format": BELGAZPROMBANK_STATEMENT_FORMAT},
    )

    assert not BankStatementCsvService._receipt_is_in_statement_scope(
        primary_account_receipt,
        statement_format=BELGAZPROMBANK_STATEMENT_FORMAT,
    )
    assert BankStatementCsvService._receipt_is_in_statement_scope(
        belagaz_receipt,
        statement_format=BELGAZPROMBANK_STATEMENT_FORMAT,
    )
    assert BankStatementCsvService._receipt_is_in_statement_scope(
        primary_account_receipt,
        statement_format=BELAGROPROMBANK_STATEMENT_FORMAT,
    )


def test_statement_format_participates_in_receipt_fingerprint():
    credit = BankStatementCsvService.parse_statement(
        _belgazprombank_csv(_belgazprombank_row())
    ).credits[0]
    other_format_credit = replace(
        credit,
        statement_format=BELAGROPROMBANK_STATEMENT_FORMAT,
    )

    assert BankStatementCsvService._fingerprint(
        credit
    ) != BankStatementCsvService._fingerprint(other_format_credit)
    receipt = BankStatementCsvService._receipt_from_credit(credit)
    assert receipt.match_meta["statement_format"] == BELGAZPROMBANK_STATEMENT_FORMAT
