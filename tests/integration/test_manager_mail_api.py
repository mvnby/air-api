from datetime import datetime

import pytest

from core.config import settings
from models import BankReceipt, OutgoingEmail, PaymentCurrency
from services.bank_receipt_service import BankReceiptImportResult


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_mail_lists_bank_receipts(async_client, db):
    db.add(
        BankReceipt(
            status="requires_review",
            operation_type="incoming_funds",
            sender_email="noreply@service.belapb.by",
            subject="Поступление средств на счет ...",
            fingerprint="receipt-list-test",
            received_at=datetime(2026, 5, 8, 14, 57),
            amount=1015,
            currency=PaymentCurrency.BYN,
            raw_body="raw",
        )
    )
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get("/api/manager/mail/bank-receipts", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["amount"] == 1015
    assert payload["items"][0]["status"] == "requires_review"


@pytest.mark.asyncio
async def test_manager_mail_import_endpoint_uses_imap_service(async_client, monkeypatch):
    async def fake_import(_session, *, limit=50):
        assert limit == 2
        return BankReceiptImportResult(processed=2, created=1, duplicates=1, failed=0, receipt_ids=[10])

    monkeypatch.setattr("routers.manager_mail.MailImapService.import_bank_receipts", fake_import)

    headers = await _auth_headers(async_client)
    response = await async_client.post("/api/manager/mail/bank-receipts/import?limit=2", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "processed": 2,
        "created": 1,
        "duplicates": 1,
        "failed": 0,
        "receipt_ids": [10],
    }


@pytest.mark.asyncio
async def test_manager_mail_send_test_endpoint_uses_smtp_service(async_client, monkeypatch):
    async def fake_send(_session, **kwargs):
        assert kwargs["to_email"] == "client@example.com"
        return OutgoingEmail(
            id=99,
            status="sent",
            recipient_email=kwargs["to_email"],
            subject=kwargs["subject"],
            body_text=kwargs["body_text"],
            from_email="a@mvn.by",
            from_name="Мастер Воздуха",
            sent_at=datetime(2026, 5, 8, 15, 0),
        )

    monkeypatch.setattr("routers.manager_mail.MailSmtpService.send_and_record", fake_send)

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        "/api/manager/mail/email/send-test",
        headers=headers,
        json={"to_email": "client@example.com", "subject": "Тест", "body_text": "Здравствуйте"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == 99
    assert payload["status"] == "sent"
    assert payload["recipient_email"] == "client@example.com"
