import pytest

from routers.manager_mail import import_manager_bank_receipts
from services.bank_receipt_service import BankReceiptImportResult
from services.mail_imap_service import MailImapService
from services.notification_service import NotificationService


@pytest.mark.asyncio
async def test_manual_bank_import_notifies_only_created_receipts(monkeypatch):
    session = object()
    notification_calls = []

    async def fake_import(received_session, *, limit):
        assert received_session is session
        assert limit == 2
        return BankReceiptImportResult(
            processed=2,
            created=1,
            duplicates=1,
            receipt_ids=[10, 11],
            created_receipt_ids=[10],
        )

    async def fake_notify(received_session, receipt_ids):
        notification_calls.append((received_session, receipt_ids))
        return 1

    monkeypatch.setattr(MailImapService, "import_bank_receipts", fake_import)
    monkeypatch.setattr(NotificationService, "notify_admins_bank_receipts_imported", fake_notify)

    response = await import_manager_bank_receipts(limit=2, session=session)

    assert response.processed == 2
    assert response.created == 1
    assert response.duplicates == 1
    assert response.receipt_ids == [10, 11]
    assert notification_calls == [(session, [10])]
