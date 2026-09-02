from datetime import datetime
from email.message import EmailMessage

import pytest

from core.config import settings
from sqlmodel import select

from models import (
    BankReceipt,
    Customer,
    CustomerType,
    Order,
    OrderProposal,
    OrderServiceLink,
    OrderStatus,
    OutgoingEmail,
    Payment,
    PaymentCurrency,
)
from services.bank_receipt_service import BankReceiptImportResult
from services.bank_receipt_service import BankReceiptService
from services.email_lead_import_job_service import EmailLeadImportJobSnapshot
from services.email_lead_intake_service import EmailLeadImportResult


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
async def test_manager_mail_auto_attaches_exact_group_bank_receipt(async_client, db):
    customer = Customer(
        tenant_id=1,
        name='ТД "Витебск Агропродукт"',
        phone="+375291234567",
        type=CustomerType.company,
        inn="300123456",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order_a = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.EXECUTION, title="Акт 1")
    order_b = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.EXECUTION, title="Акт 2")
    db.add_all([order_a, order_b])
    await db.commit()
    await db.refresh(order_a)
    await db.refresh(order_b)

    proposal_a = OrderProposal(order_id=order_a.id, name="Основное", is_selected=True)
    proposal_b = OrderProposal(order_id=order_b.id, name="Основное", is_selected=True)
    db.add_all([proposal_a, proposal_b])
    await db.commit()
    await db.refresh(proposal_a)
    await db.refresh(proposal_b)

    db.add_all(
        [
            OrderServiceLink(order_id=order_a.id, proposal_id=proposal_a.id, title="Монтаж", quantity=1, price=2600, cost=0),
            OrderServiceLink(order_id=order_b.id, proposal_id=proposal_b.id, title="ТО", quantity=1, price=2300, cost=0),
        ]
    )
    receipt = BankReceipt(
        status="new",
        operation_type="incoming_funds",
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет",
        fingerprint="group-receipt-test",
        received_at=datetime(2026, 6, 29, 11, 30),
        amount=4900,
        currency=PaymentCurrency.BYN,
        payer_name='ТД "Витебск Агропродукт"',
        payer_unp="300123456",
        payment_purpose="Оплата по актам за июнь",
        raw_body="raw",
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)

    await BankReceiptService.match_receipt(db, receipt)
    await db.commit()
    await db.refresh(receipt)

    assert receipt.status == "matched"
    assert receipt.match_meta["reason"] == "group_balance_due_exact"
    assert receipt.match_meta["auto_group_attached"] is True
    assert receipt.match_meta["group_match"]["is_exact"] is True
    assert receipt.match_meta["group_match"]["total_balance_due"] == 4900
    assert set(receipt.match_meta["group_match"]["order_ids"]) == {order_a.id, order_b.id}
    assert set(receipt.match_meta["group_order_ids"]) == {order_a.id, order_b.id}
    assert len(receipt.match_meta["group_payment_ids"]) == 2

    payments = (
        await db.execute(select(Payment).where(Payment.bank_receipt_id == receipt.id).order_by(Payment.amount))
    ).scalars().all()
    assert [payment.amount for payment in payments] == [2300, 2600]

    await db.refresh(order_a)
    await db.refresh(order_b)
    await BankReceiptService.update_receipt_status(db, receipt_id=receipt.id, status="requires_review", reason="rollback")
    await db.refresh(order_a)
    await db.refresh(order_b)
    assert (await db.execute(select(Payment).where(Payment.bank_receipt_id == receipt.id))).scalars().all() == []


@pytest.mark.asyncio
async def test_manager_mail_manually_attaches_review_group_bank_receipt(async_client, db):
    customer = Customer(
        tenant_id=1,
        name='ТД "Витебск Агропродукт"',
        phone="+375291234568",
        type=CustomerType.company,
        inn="300123457",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order_a = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.EXECUTION, title="Акт 1")
    order_b = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.EXECUTION, title="Акт 2")
    db.add_all([order_a, order_b])
    await db.commit()
    await db.refresh(order_a)
    await db.refresh(order_b)

    db.add_all(
        [
            OrderServiceLink(order_id=order_a.id, title="Монтаж", quantity=1, price=2700, cost=0),
            OrderServiceLink(order_id=order_b.id, title="ТО", quantity=1, price=2200, cost=0),
        ]
    )
    receipt = BankReceipt(
        status="requires_review",
        operation_type="incoming_funds",
        sender_email="bank-statement@local",
        subject="Bank statement CSV import",
        fingerprint="manual-group-receipt-test",
        received_at=datetime(2026, 6, 29, 11, 30),
        amount=4900,
        currency=PaymentCurrency.BYN,
        payer_name='ТД "Витебск Агропродукт"',
        payer_unp="300123457",
        payment_purpose="Оплата по актам за июнь",
        raw_body="raw",
        match_meta={"group_match": {"order_ids": [order_a.id, order_b.id]}},
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/mail/bank-receipts/{receipt.id}/attach-group",
        headers=headers,
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "matched"
    assert payload["match_meta"]["manual_group_attached"] is True
    assert set(payload["match_meta"]["group_order_ids"]) == {order_a.id, order_b.id}
    payments = (
        await db.execute(select(Payment).where(Payment.bank_receipt_id == receipt.id).order_by(Payment.amount))
    ).scalars().all()
    assert [payment.amount for payment in payments] == [2200, 2700]


@pytest.mark.asyncio
async def test_manager_mail_attaches_budget_payer_receipt_to_explicit_order(async_client, db):
    customer = Customer(
        tenant_id=1,
        name="Заказчик бюджетного платежа",
        phone="+375291234570",
        type=CustomerType.company,
        inn="390999002",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=customer.id,
        status=OrderStatus.EXECUTION,
        title="Бюджетный заказ",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    db.add(OrderServiceLink(order_id=order.id, title="Работы", quantity=1, price=1460, cost=0))

    receipt = BankReceipt(
        status="requires_review",
        operation_type="incoming_funds",
        sender_email="bank-statement@local",
        subject="Бюджетное поступление",
        fingerprint="manual-budget-payer-api-test",
        received_at=datetime(2026, 9, 1, 10, 0),
        amount=1460,
        currency=PaymentCurrency.BYN,
        payer_name="Главное управление МФ Республики Беларусь по Витебской области",
        payer_unp="300594330",
        payment_purpose="Оплата через бюджет",
        raw_body="raw",
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        f"/api/manager/mail/bank-receipts/{receipt.id}/attach",
        headers=headers,
        json={"order_id": order.id, "payment_type": "postpayment"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "matched"
    assert payload["matched_order_id"] == order.id
    assert payload["allocated_amount"] == 1460
    assert payload["unallocated_amount"] == 0
    assert payload["match_meta"]["manual_selected_order_id"] == order.id
    assert payload["match_meta"]["manual_payer_unp_override"] is True
    payment = (
        await db.execute(select(Payment).where(Payment.bank_receipt_id == receipt.id))
    ).scalar_one()
    assert payment.order_id == order.id


@pytest.mark.asyncio
async def test_manager_mail_replaces_partial_bank_receipt_allocations(async_client, db):
    customer = Customer(
        tenant_id=1,
        name="ООО Частичное распределение",
        phone="+375291234569",
        type=CustomerType.company,
        inn="300123458",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    order_a = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.EXECUTION, title="Акт 1")
    order_b = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.EXECUTION, title="Акт 2")
    db.add_all([order_a, order_b])
    await db.commit()
    await db.refresh(order_a)
    await db.refresh(order_b)
    db.add_all(
        [
            OrderServiceLink(order_id=order_a.id, title="Работы", quantity=1, price=500, cost=0),
            OrderServiceLink(order_id=order_b.id, title="Работы", quantity=1, price=880, cost=0),
        ]
    )
    receipt = BankReceipt(
        status="requires_review",
        operation_type="incoming_funds",
        sender_email="bank-statement@local",
        subject="Поступление с остатком",
        fingerprint="partial-allocation-api-test",
        received_at=datetime(2026, 7, 23, 12, 0),
        amount=1400,
        currency=PaymentCurrency.BYN,
        payer_name=customer.name,
        payer_unp=customer.inn,
        payment_purpose="Оплата двух актов",
        raw_body="raw",
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)
    headers = await _auth_headers(async_client)

    preview = await async_client.get(
        f"/api/manager/mail/bank-receipts/{receipt.id}/allocation",
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert {item["order_id"] for item in preview.json()["orders"]} == {order_a.id, order_b.id}

    response = await async_client.put(
        f"/api/manager/mail/bank-receipts/{receipt.id}/allocations",
        headers=headers,
        json={
            "allocations": [
                {"order_id": order_a.id, "amount": 500},
                {"order_id": order_b.id, "amount": 880},
            ],
            "payment_type": "postpayment",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "partially_allocated"
    assert payload["allocated_amount"] == 1380
    assert payload["unallocated_amount"] == 20
    assert payload["allocation_count"] == 2

    replacement = await async_client.put(
        f"/api/manager/mail/bank-receipts/{receipt.id}/allocations",
        headers=headers,
        json={
            "allocations": [
                {"order_id": order_a.id, "amount": 400},
                {"order_id": order_b.id, "amount": 600},
            ]
        },
    )
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["allocated_amount"] == 1000
    payments = (
        await db.execute(
            select(Payment).where(Payment.bank_receipt_id == receipt.id).order_by(Payment.amount)
        )
    ).scalars().all()
    assert [payment.amount for payment in payments] == [400, 600]


@pytest.mark.asyncio
async def test_manager_mail_import_endpoint_uses_imap_service(async_client, monkeypatch):
    notified_receipt_ids = []

    async def fake_import(_session, *, limit=50):
        assert limit == 2
        return BankReceiptImportResult(
            processed=2,
            created=1,
            duplicates=1,
            failed=0,
            receipt_ids=[10],
            created_receipt_ids=[10],
        )

    async def fake_notify(_session, receipt_ids, *, tenant_scope):
        assert tenant_scope.is_system is True
        notified_receipt_ids.extend(receipt_ids)
        return 1

    monkeypatch.setattr("routers.manager_mail.MailImapService.import_bank_receipts", fake_import)
    monkeypatch.setattr(
        "routers.manager_mail.NotificationService.notify_admins_bank_receipts_imported",
        fake_notify,
    )

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
    assert notified_receipt_ids == [10]


@pytest.mark.asyncio
async def test_manager_mail_lead_import_endpoint_uses_imap_service(async_client, monkeypatch):
    async def fake_start(*, dry_run=False, lookback_days=None):
        assert dry_run is True
        assert lookback_days == 7
        result = EmailLeadImportResult(
            processed=3,
            scanned_since="2026-05-23T09:00:00",
            last_import_at=None,
            candidates=2,
            ai_checked=2,
            would_create=1,
            created=1,
            duplicates=1,
            rejected=0,
            failed=0,
            lead_ids=[42, 41],
            created_lead_ids=[42],
            order_ids=[52, 51],
            created_order_ids=[52],
        )
        return EmailLeadImportJobSnapshot(
            status="running",
            source="manual",
            dry_run=dry_run,
            lookback_days=lookback_days,
            message="Импорт email-лидов запущен в фоне.",
            result=result,
        )

    monkeypatch.setattr("routers.manager_mail.EmailLeadImportJobService.start_manual_import", fake_start)

    headers = await _auth_headers(async_client)
    response = await async_client.post("/api/manager/mail/leads/import?dry_run=true&lookback_days=7", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "running",
        "source": "manual",
        "dry_run": True,
        "lookback_days": 7,
        "started_at": None,
        "finished_at": None,
        "last_import_at": None,
        "notified_admins": 0,
        "already_running": False,
        "error": None,
        "message": "Импорт email-лидов запущен в фоне.",
        "result": {
            "processed": 3,
            "scanned_since": "2026-05-23T09:00:00",
            "last_import_at": None,
            "candidates": 2,
            "ai_checked": 2,
            "would_create": 1,
            "created": 1,
            "duplicates": 1,
            "rejected": 0,
            "failed": 0,
            "lead_ids": [42, 41],
            "created_lead_ids": [42],
            "order_ids": [52, 51],
            "created_order_ids": [52],
            "decisions": [],
        },
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


@pytest.mark.asyncio
async def test_manager_mail_lists_outgoing_emails_with_failures(async_client, db):
    customer = Customer(tenant_id=1, name="Outbox Client", phone="+375291112233", email="client@example.com", type=CustomerType.company)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.NEGOTIATION, title="Документы на отправку")
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add_all(
        [
            OutgoingEmail(
                status="sent",
                order_id=order.id,
                customer_id=customer.id,
                recipient_email="client@example.com",
                subject="Успешное письмо",
                body_text="sent",
                sent_at=datetime(2026, 7, 8, 10, 0),
                created_at=datetime(2026, 7, 8, 9, 59),
            ),
            OutgoingEmail(
                status="failed",
                order_id=order.id,
                customer_id=customer.id,
                recipient_email="client@example.com",
                subject="Ошибка доставки",
                body_text="failed",
                error="[Errno 101] Network is unreachable",
                created_at=datetime(2026, 7, 8, 10, 1),
            ),
            OutgoingEmail(
                status="pending",
                recipient_email="other@example.com",
                subject="Другое письмо",
                body_text="pending",
                created_at=datetime(2026, 7, 8, 10, 2),
            ),
        ]
    )
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get(
        "/api/manager/mail/outgoing-emails",
        headers=headers,
        params={"status": "failed", "q": "доставки"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["status"] == "failed"
    assert item["customer_name"] == "Outbox Client"
    assert item["order_title"] == "Документы на отправку"
    assert item["error"] == "[Errno 101] Network is unreachable"


@pytest.mark.asyncio
async def test_manager_mail_lists_order_outgoing_emails(async_client, db):
    customer = Customer(tenant_id=1, name="Order Mail Client", phone="+375291112244", email="mail@example.com", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.NEGOTIATION, title="Заказ с письмами")
    other_order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.NEGOTIATION, title="Другой заказ")
    db.add_all([order, other_order])
    await db.commit()
    await db.refresh(order)
    await db.refresh(other_order)

    db.add_all(
        [
            OutgoingEmail(status="sent", order_id=order.id, customer_id=customer.id, recipient_email="mail@example.com", subject="Документы", body_text="1"),
            OutgoingEmail(status="failed", order_id=other_order.id, customer_id=customer.id, recipient_email="mail@example.com", subject="Другое", body_text="2"),
        ]
    )
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get(f"/api/manager/mail/orders/{order.id}/outgoing-emails", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["order_id"] == order.id
    assert payload["items"][0]["subject"] == "Документы"


@pytest.mark.asyncio
async def test_manager_mail_get_outgoing_email_detail_includes_retry_chain(async_client, db):
    original = OutgoingEmail(
        status="failed",
        recipient_email="client@example.com",
        subject="Документы",
        body_text="Не ушло",
        error="[Errno 101] Network is unreachable",
    )
    db.add(original)
    await db.commit()
    await db.refresh(original)

    retry = OutgoingEmail(
        status="sent",
        retry_of_email_id=original.id,
        recipient_email="client@example.com",
        subject="Документы",
        body_text="Ушло",
        sent_at=datetime(2026, 7, 8, 11, 0),
    )
    db.add(retry)
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get(f"/api/manager/mail/outgoing-emails/{original.id}", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == original.id
    assert [item["status"] for item in payload["retry_attempts"]] == ["failed", "sent"]


@pytest.mark.asyncio
async def test_manager_mail_retry_failed_email_creates_new_attempt(async_client, db, monkeypatch):
    original = OutgoingEmail(
        status="failed",
        recipient_email="client@example.com",
        subject="Повторить",
        body_text="Текст письма",
        error="[Errno 101] Network is unreachable",
    )
    db.add(original)
    await db.commit()
    await db.refresh(original)

    sent_messages = []

    def fake_build_message(**kwargs):
        msg = EmailMessage()
        msg["To"] = kwargs["to_email"]
        msg["Subject"] = kwargs["subject"]
        msg.set_content(kwargs["body_text"] or "")
        return msg

    def fake_send_message(message):
        sent_messages.append(message)

    monkeypatch.setattr("services.outgoing_email_service.MailSmtpService.build_message", fake_build_message)
    monkeypatch.setattr("services.outgoing_email_service.MailSmtpService.send_message", fake_send_message)
    monkeypatch.setattr("services.outgoing_email_service.MailSmtpService._configured_from_email", lambda: "noreply@example.com")

    headers = await _auth_headers(async_client)
    response = await async_client.post(f"/api/manager/mail/outgoing-emails/{original.id}/retry", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] != original.id
    assert payload["retry_of_email_id"] == original.id
    assert payload["status"] == "sent"
    assert len(sent_messages) == 1

    refreshed_original = await db.get(OutgoingEmail, original.id)
    assert refreshed_original.status == "failed"
    assert refreshed_original.error == "[Errno 101] Network is unreachable"


@pytest.mark.asyncio
async def test_manager_mail_retry_attachment_email_requires_snapshot(async_client, db, monkeypatch):
    original = OutgoingEmail(
        status="failed",
        recipient_email="client@example.com",
        subject="Документы",
        body_text="См. вложение",
        error="[Errno 101] Network is unreachable",
        attachments=[{"filename": "invoice.pdf", "mime_type": "application/pdf", "size": 100}],
    )
    db.add(original)
    await db.commit()
    await db.refresh(original)

    sent_messages = []
    monkeypatch.setattr("services.outgoing_email_service.MailSmtpService.send_message", lambda message: sent_messages.append(message))

    headers = await _auth_headers(async_client)
    response = await async_client.post(f"/api/manager/mail/outgoing-emails/{original.id}/retry", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] != original.id
    assert payload["retry_of_email_id"] == original.id
    assert payload["status"] == "failed"
    assert "snapshot PDF" in payload["error"]
    assert sent_messages == []


@pytest.mark.asyncio
async def test_manager_mail_send_order_email_passes_document_ids(async_client, monkeypatch):
    async def fake_send(_session, **kwargs):
        assert kwargs["order_id"] == 123
        assert kwargs["to_email"] == "client@example.com"
        assert kwargs["document_ids"] == [10, 11]
        return OutgoingEmail(
            id=100,
            status="sent",
            order_id=kwargs["order_id"],
            recipient_email=kwargs["to_email"],
            subject=kwargs["subject"],
            body_text=kwargs["body_text"],
            from_email="a@mvn.by",
            from_name="Мастер Воздуха",
            sent_at=datetime(2026, 5, 8, 15, 10),
            attachments=[
                {"filename": "КП-2026-001.pdf", "mime_type": "application/pdf", "size": 100},
                {"filename": "СЧ-2026-001.pdf", "mime_type": "application/pdf", "size": 100},
            ],
        )

    monkeypatch.setattr("routers.manager_mail.MailSmtpService.send_order_email", fake_send)

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        "/api/manager/mail/orders/123/email",
        headers=headers,
        json={
            "to_email": "client@example.com",
            "subject": "Коммерческое предложение",
            "body_text": "Здравствуйте, документы во вложении.",
            "document_ids": [10, 11],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == 100
    assert payload["order_id"] == 123
    assert len(payload["attachments"]) == 2


@pytest.mark.asyncio
async def test_manager_mail_composes_adaptive_order_email(async_client, monkeypatch):
    async def fake_compose(_session, **kwargs):
        tenant_scope = kwargs.pop("tenant_scope")
        assert tenant_scope.is_system is True
        assert kwargs == {
            "order_id": 123,
            "document_ids": [10, 11],
            "template_key": "auto",
        }
        return {
            "template_key": "documents",
            "template_options": [
                {"key": "auto", "label": "Автоматически", "requires_documents": True},
                {"key": "documents", "label": "Комплект документов", "requires_documents": True},
            ],
            "subject": "Счёт и договор на техническое обслуживание кондиционеров",
            "body_text": "Добрый день!\n\nНаправляем счёт и договор.",
            "document_ids": [10, 11],
            "document_labels": ["Счёт СЧ-10", "Договор Д-11"],
            "missing_requisites": [{"key": "signer_name", "label": "ФИО подписанта"}],
        }

    monkeypatch.setattr("routers.manager_mail.OrderEmailTemplateService.compose", fake_compose)

    headers = await _auth_headers(async_client)
    response = await async_client.post(
        "/api/manager/mail/orders/123/compose",
        headers=headers,
        json={"document_ids": [10, 11], "template_key": "auto"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["template_key"] == "documents"
    assert payload["subject"] == "Счёт и договор на техническое обслуживание кондиционеров"
    assert payload["missing_requisites"] == [{"key": "signer_name", "label": "ФИО подписанта"}]
