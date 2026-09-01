import csv
from datetime import datetime
from io import StringIO

import pytest
from sqlmodel import select

from core.config import settings
from models import BankReceipt
from services.bank_statement_csv_parser import BELGAZPROMBANK_STATEMENT_FORMAT


def _belgazprombank_statement() -> bytes:
    rows = [
        [
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
        ],
        [
            "01.09.2026",
            "000041",
            "06",
            "BYN",
            "TESTBY2X",
            "Тестовый поставщик",
            "100000001",
            "BY00TEST00000000000000000001",
            "25.00",
            "",
            "",
            "Банковская комиссия",
        ],
        [
            "01.09.2026",
            "000042",
            "01",
            "BYN",
            "TESTBY2X",
            "Тестовый покупатель",
            "100000002",
            "BY00TEST00000000000000000002",
            "",
            "1460.00",
            "",
            "Оплата по тестовому счету 42",
        ],
    ]
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


async def _auth_headers(async_client):
    response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_manager_imports_belgazprombank_statement_without_cross_account_flags(
    async_client,
    db,
):
    primary_account_receipt = BankReceipt(
        status="requires_review",
        operation_type="incoming_funds",
        sender_email="primary-bank@example.test",
        subject="Primary account receipt",
        fingerprint="primary-account-statement-scope",
        received_at=datetime(2026, 9, 1),
        amount=500,
        payer_unp="100000099",
        payment_document_number="99",
        raw_body="synthetic",
    )
    db.add(primary_account_receipt)
    await db.commit()

    response = await async_client.post(
        "/api/manager/mail/bank-receipts/import-statement",
        headers=await _auth_headers(async_client),
        files={"file": ("belgazprombank.csv", _belgazprombank_statement(), "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == 2
    assert payload["credit_rows"] == 1
    assert payload["skipped"] == 1
    assert payload["created"] == 1
    assert payload["matched_existing"] == 0
    assert payload["suspicious"] == 0

    receipts = (await db.execute(select(BankReceipt))).scalars().all()
    imported = next(
        receipt
        for receipt in receipts
        if (receipt.match_meta or {}).get("statement_format")
        == BELGAZPROMBANK_STATEMENT_FORMAT
    )
    assert imported.amount == 1460
    assert imported.payer_unp == "100000002"
    assert imported.payment_document_number == "000042"
    assert imported.payment_purpose == "Оплата по тестовому счету 42"
    assert "missing_in_last_statement" not in (primary_account_receipt.match_meta or {})
