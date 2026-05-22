from pathlib import Path
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.config import settings
from models import BankReceipt, Customer, Order, OrderDocument, OrderServiceLink, OutgoingEmail, Payment, PaymentCurrency
from services.bank_email_parser_service import BankEmailParserService
from services.bank_receipt_service import BankReceiptService
from services.bank_statement_csv_service import BankStatementCsvService
from services.bot_service import BotService
from services.mail_smtp_service import MailAttachment, MailSmtpService
from services.notification_service import NotificationService


SAMPLE_BANK_EMAIL = """
Добрый день!

Уважаемый клиент Индивидуальный предприниматель Янулевич Дмитрий Викторович, на Ваш банковский счет №BY93BAPB3013W294700100000000 08.05.26 14:57 поступили денежные средства в размере 1 015 BYN от ДОЧЕРНЕЕ КОММУНАЛЬНОЕ УНИТАРНОЕ ПРЕДПРИЯТИЕ "УПРАВЛЕНИЕ КАПИТАЛЬНОГО СТРОИТЕЛЬСТВА Г. ВИТЕБСКА", УНП 300200572 со счета №BY25AKBB30120379400272000000. Реквизиты платежного документа: 1 № 008049, назначение: ОПЛАТА ЗА РЕМОНТ И ОБСЛУЖИВАНИЕ КОНДИЦИОНЕРА СОГЛАСНО АКТУ N7 ОТ 27.04.26 НДС НЕТ. Остаток по счету после зачисления составляет 4 662.26 BYN.
"""

MULTI_ACT_BANK_EMAIL = """
Добрый день!

Уважаемый клиент Индивидуальный предприниматель Янулевич Дмитрий Викторович, на Ваш банковский счет №BY93BAPB3013W294700100000000 08.05.26 14:57 поступили денежные средства в размере 1 015 BYN от ДОЧЕРНЕЕ КОММУНАЛЬНОЕ УНИТАРНОЕ ПРЕДПРИЯТИЕ "УПРАВЛЕНИЕ КАПИТАЛЬНОГО СТРОИТЕЛЬСТВА Г. ВИТЕБСКА", УНП 300200572 со счета №BY25AKBB30120379400272000000. Реквизиты платежного документа: 1 № 008049, назначение: ОПЛАТА ЗА РЕМОНТ И ОБСЛУЖИВАНИЕ КОНДИЦИОНЕРА СОГЛАСНО АКТУ N7 ОТ 27.04.26, N8 ОТ 30.04.2026 НДС НЕТ. Остаток по счету после зачисления составляет 4 662.26 BYN.
"""

SAMPLE_STATEMENT_CSV = """;Выписка по счету №BY93BAPB3013W294700100000000 за период с 08.05.2026 по 22.05.2026;
;
Код валюты: BYN;
;
Код банка;Счет-корреспондент;Номер документа;Обороты: дебет;Обороты: кредит;В эквиваленте;Дата операции;Назначение;Наименование контрагента;УНП контрагента;
AKBBBY2X;="BY25AKBB30120379400272000000";="008049";;1015,00;1015,00;08.05.2026;OTHR 121601, ОПЛАТА ЗА РЕМОНТ И ОБСЛУЖИВАНИЕ КОНДИЦИОНЕРА СОГЛАСНО АКТУ N7 ОТ 27.04.26, N8 ОТ 30.04.2026 НДС НЕТ;ДОЧЕРНЕЕ КОММУНАЛЬНОЕ УНИТАРНОЕ ПРЕДПРИЯТИЕ "УПРАВЛЕНИЕ КАПИТАЛЬНОГО СТРОИТЕЛЬСТВА Г. ВИТЕБСКА";300200572;
PJCBBY2X;="BY44PJCB30120493741000000933";="17";;420,00;420,00;22.05.2026;OTHR 190401, ОПЛАТА СОГЛАСНО СЧЕТА 61 ОТ 07.05.2026 ТЕХНИЧЕСКОЕ ОБСЛУЖИВАНИЕ;ООО "МЕГАХЕНД";192663084;
Итого оборотов;;;;1435,00;;;;;
"""


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mail_services.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_bank_email_parser_extracts_real_belagroprombank_format():
    parsed = BankEmailParserService.parse(
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет Индивидуальный предприниматель Янулевич Дмитрий Викторович 08.05.26 14:57",
        raw_body=SAMPLE_BANK_EMAIL,
        message_id="<bank-1@example.test>",
    )

    assert parsed.amount == 1015
    assert parsed.currency == PaymentCurrency.BYN
    assert parsed.payer_unp == "300200572"
    assert parsed.payer_name == 'ДОЧЕРНЕЕ КОММУНАЛЬНОЕ УНИТАРНОЕ ПРЕДПРИЯТИЕ "УПРАВЛЕНИЕ КАПИТАЛЬНОГО СТРОИТЕЛЬСТВА Г. ВИТЕБСКА"'
    assert parsed.received_at.year == 2026
    assert parsed.received_at.month == 5
    assert parsed.received_at.day == 8
    assert parsed.received_at.hour == 14
    assert parsed.received_at.minute == 57
    assert parsed.our_account == "BY93BAPB3013W294700100000000"
    assert parsed.payer_account == "BY25AKBB30120379400272000000"
    assert parsed.payment_document_number == "008049"
    assert "АКТУ N7" in parsed.payment_purpose
    assert parsed.account_balance_after == 4662.26


@pytest.mark.asyncio
async def test_bank_receipt_dedupes_and_creates_exact_order_payment(sqlite_session):
    customer = Customer(name="УКС Витебск", phone="+375291111111", type="company", inn="300200572")
    sqlite_session.add(customer)
    await sqlite_session.commit()
    await sqlite_session.refresh(customer)

    order = Order(customer_id=customer.id, status="execution")
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    sqlite_session.add(OrderServiceLink(order_id=order.id, title="Ремонт", quantity=1, price=1015, cost=0))
    await sqlite_session.commit()

    receipt, created = await BankReceiptService.process_email(
        sqlite_session,
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет Индивидуальный предприниматель Янулевич Дмитрий Викторович 08.05.26 14:57",
        raw_body=SAMPLE_BANK_EMAIL,
        message_id="<bank-1@example.test>",
    )
    assert created is True
    assert receipt.status == "matched"
    assert receipt.matched_order_id == order.id
    assert receipt.matched_payment_id is not None

    duplicate, created_again = await BankReceiptService.process_email(
        sqlite_session,
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет Индивидуальный предприниматель Янулевич Дмитрий Викторович 08.05.26 14:57",
        raw_body=SAMPLE_BANK_EMAIL,
        message_id="<bank-1@example.test>",
    )
    assert created_again is False
    assert duplicate.id == receipt.id

    payments = (await sqlite_session.execute(select(Payment))).scalars().all()
    receipts = (await sqlite_session.execute(select(BankReceipt))).scalars().all()
    assert len(payments) == 1
    assert len(receipts) == 1
    assert payments[0].bank_receipt_id == receipt.id


@pytest.mark.asyncio
async def test_bank_receipt_multi_act_payment_requires_review(sqlite_session):
    customer = Customer(name="УКС Витебск", phone="+375291111111", type="company", inn="300200572")
    sqlite_session.add(customer)
    await sqlite_session.commit()
    await sqlite_session.refresh(customer)

    order = Order(customer_id=customer.id, status="execution")
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    sqlite_session.add(OrderServiceLink(order_id=order.id, title="Ремонт", quantity=1, price=1015, cost=0))
    await sqlite_session.commit()

    receipt, created = await BankReceiptService.process_email(
        sqlite_session,
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет Индивидуальный предприниматель Янулевич Дмитрий Викторович 08.05.26 14:57",
        raw_body=MULTI_ACT_BANK_EMAIL,
        message_id="<bank-2@example.test>",
    )
    assert created is True
    assert receipt.status == "requires_review"
    assert receipt.match_meta["reason"] == "multi_document_payment"

    payments = (await sqlite_session.execute(select(Payment))).scalars().all()
    assert payments == []


@pytest.mark.asyncio
async def test_bank_receipt_can_be_manually_attached_to_order(sqlite_session):
    customer = Customer(name="УКС Витебск", phone="+375291111111", type="company", inn="300200572")
    sqlite_session.add(customer)
    await sqlite_session.commit()
    await sqlite_session.refresh(customer)

    order = Order(customer_id=customer.id, status="execution")
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    sqlite_session.add(OrderServiceLink(order_id=order.id, title="Ремонт", quantity=1, price=1015, cost=0))
    await sqlite_session.commit()

    receipt, created = await BankReceiptService.process_email(
        sqlite_session,
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет Индивидуальный предприниматель Янулевич Дмитрий Викторович 08.05.26 14:57",
        raw_body=MULTI_ACT_BANK_EMAIL,
        message_id="<bank-manual@example.test>",
    )
    assert created is True
    assert receipt.status == "requires_review"

    attached = await BankReceiptService.attach_receipt_to_order(
        sqlite_session,
        receipt_id=receipt.id,
        order_id=order.id,
        payment_type="postpayment",
    )

    assert attached.status == "matched"
    assert attached.matched_order_id == order.id
    assert attached.matched_payment_id is not None
    payments = (await sqlite_session.execute(select(Payment))).scalars().all()
    assert len(payments) == 1
    assert payments[0].bank_receipt_id == receipt.id


@pytest.mark.asyncio
async def test_bank_receipt_can_be_marked_void_and_reverses_linked_payment(sqlite_session):
    customer = Customer(name="Мегахенд", phone="+375291111113", type="company", inn="192663084")
    sqlite_session.add(customer)
    await sqlite_session.commit()
    await sqlite_session.refresh(customer)

    order = Order(customer_id=customer.id, status="execution")
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    sqlite_session.add(OrderServiceLink(order_id=order.id, title="Обслуживание", quantity=1, price=420, cost=0))
    await sqlite_session.commit()

    raw_body = SAMPLE_BANK_EMAIL.replace("1 015 BYN", "420 BYN").replace("300200572", "192663084")
    receipt, created = await BankReceiptService.process_email(
        sqlite_session,
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет Индивидуальный предприниматель Янулевич Дмитрий Викторович 08.05.26 14:57",
        raw_body=raw_body,
        message_id="<bank-void@example.test>",
    )
    assert created is True
    assert receipt.status == "matched"
    assert receipt.matched_payment_id is not None

    voided = await BankReceiptService.update_receipt_status(
        sqlite_session,
        receipt_id=receipt.id,
        status="void",
        reason="Отозван банком",
    )

    assert voided.status == "void"
    assert voided.matched_order_id is None
    assert voided.matched_payment_id is None
    assert voided.match_meta["manual_reason"] == "Отозван банком"
    payments = (await sqlite_session.execute(select(Payment))).scalars().all()
    assert payments == []
    refreshed_order = await sqlite_session.get(Order, order.id)
    assert refreshed_order.balance_due == 420


def test_bank_statement_csv_parser_reads_credit_rows():
    credits = BankStatementCsvService.parse(SAMPLE_STATEMENT_CSV.encode("cp1251"))

    assert len(credits) == 2
    assert credits[0].amount == 1015
    assert credits[0].payer_unp == "300200572"
    assert credits[0].payment_document_number == "008049"
    assert credits[0].operation_date.year == 2026
    assert not credits[0].payment_purpose.startswith("OTHR")
    assert credits[1].payer_name == 'ООО "МЕГАХЕНД"'


@pytest.mark.asyncio
async def test_bank_statement_import_creates_missing_and_flags_duplicate_receipts(sqlite_session):
    customer = Customer(name="Мегахенд", phone="+375291111113", type="company", inn="192663084")
    sqlite_session.add(customer)
    await sqlite_session.commit()
    await sqlite_session.refresh(customer)

    order = Order(customer_id=customer.id, status="execution")
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    sqlite_session.add(OrderServiceLink(order_id=order.id, title="Обслуживание", quantity=1, price=420, cost=0))

    duplicate_receipt = BankReceipt(
        status="requires_review",
        operation_type="incoming_funds",
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет",
        message_id="<duplicate-statement@example.test>",
        fingerprint="duplicate-statement-fingerprint",
        received_at=datetime(2026, 5, 8, 15, 0),
        amount=1015,
        currency=PaymentCurrency.BYN,
        payer_name="УКС",
        payer_unp="300200572",
        payment_document_number="008049",
        payment_purpose="ОПЛАТА ЗА РЕМОНТ",
        raw_body="raw",
    )
    sqlite_session.add(duplicate_receipt)
    await sqlite_session.commit()

    result = await BankStatementCsvService.import_statement(sqlite_session, SAMPLE_STATEMENT_CSV.encode("cp1251"))

    assert result.credit_rows == 2
    assert result.matched_existing == 1
    assert result.created == 1
    assert duplicate_receipt.id in result.matched_receipt_ids
    receipts = (await sqlite_session.execute(select(BankReceipt))).scalars().all()
    assert len(receipts) == 2
    megahand = next(item for item in receipts if item.payer_unp == "192663084")
    assert megahand.status == "matched"
    assert megahand.matched_order_id == order.id
    assert megahand.match_meta["source"] == "bank_statement_csv"


@pytest.mark.asyncio
async def test_bank_receipt_import_notification_goes_to_admins(sqlite_session, monkeypatch):
    receipt = BankReceipt(
        status="requires_review",
        operation_type="incoming_funds",
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет",
        message_id="<notify-bank@example.test>",
        fingerprint="notify-bank-fingerprint",
        amount=1440,
        currency=PaymentCurrency.BYN,
        payer_name="ООО Тест",
        payer_unp="300203571",
        payment_document_number="008050",
        payment_purpose="Оплата по договору Д-2026-010",
        match_meta={"candidate_order_ids": [50]},
        raw_body="raw",
    )
    matched = BankReceipt(
        status="matched",
        operation_type="incoming_funds",
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет",
        message_id="<matched-bank@example.test>",
        fingerprint="matched-bank-fingerprint",
        amount=1015,
        currency=PaymentCurrency.BYN,
        payer_name="ООО Уже разнесено",
        payer_unp="300200572",
        matched_order_id=61,
        raw_body="raw",
    )
    sqlite_session.add(receipt)
    sqlite_session.add(matched)
    await sqlite_session.commit()
    await sqlite_session.refresh(receipt)
    await sqlite_session.refresh(matched)

    sent: list[tuple[int, str]] = []

    async def fake_send_message(user_id: int, text: str):
        sent.append((user_id, text))

    monkeypatch.setattr(settings, "ADMIN_IDS", "101,202")
    monkeypatch.setattr(settings, "ADMIN_ID", 0)
    monkeypatch.setattr(BotService, "send_message", fake_send_message)

    sent_count = await NotificationService.notify_admins_bank_receipts_imported(
        sqlite_session,
        [receipt.id, matched.id],
    )

    assert sent_count == 2
    assert [item[0] for item in sent] == [101, 202]
    assert "Новые банковские поступления: 2" in sent[0][1]
    assert "Разнесено автоматически: 1" in sent[0][1]
    assert "Требует проверки: 1" in sent[0][1]
    assert "ООО Тест" in sent[0][1]
    assert "#50" in sent[0][1]
    assert "ООО Уже разнесено" in sent[0][1]
    assert "разнесено в заказ #61" in sent[0][1]


def test_smtp_builds_utf8_message_and_sanitizes_errors(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_SMTP_USERNAME", "a@mvn.by")
    monkeypatch.setattr(settings, "MAIL_SMTP_PASSWORD", "super-secret")
    monkeypatch.setattr(settings, "MAIL_FROM_EMAIL", "a@mvn.by")
    monkeypatch.setattr(settings, "MAIL_FROM_NAME", "Мастер Воздуха")

    message = MailSmtpService.build_message(
        to_email="client@example.com",
        subject="Счет и акт",
        body_text="Здравствуйте!",
        body_html="<p>Здравствуйте!</p>",
        attachments=[MailAttachment(filename="акт.pdf", content=b"pdf", mime_type="application/pdf")],
    )

    rendered = message.as_string()
    assert "client@example.com" in rendered
    assert "application/pdf" in rendered
    assert "super-secret" not in MailSmtpService._sanitize_error(RuntimeError("failed with super-secret"))


@pytest.mark.asyncio
async def test_send_order_email_attaches_documents_and_marks_offer_sent(sqlite_session, monkeypatch):
    monkeypatch.setattr(settings, "MAIL_SMTP_USERNAME", "a@mvn.by")
    monkeypatch.setattr(settings, "MAIL_SMTP_PASSWORD", "super-secret")
    monkeypatch.setattr(settings, "MAIL_FROM_EMAIL", "a@mvn.by")
    monkeypatch.setattr(settings, "MAIL_FROM_NAME", "Мастер Воздуха")

    customer = Customer(name="ООО Клиент", phone="+375291111111", type="company", email="client@example.com")
    sqlite_session.add(customer)
    await sqlite_session.commit()
    await sqlite_session.refresh(customer)

    order = Order(customer_id=customer.id, status="negotiation", proposal_status="draft")
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    offer = OrderDocument(
        order_id=order.id,
        doc_type="offer",
        number="КП-2026-001",
        google_file_id="offer-file",
        google_edit_url="https://docs.example/offer",
    )
    invoice = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="СЧ-2026-001",
        google_file_id="invoice-file",
        google_edit_url="https://docs.example/invoice",
    )
    sqlite_session.add(offer)
    sqlite_session.add(invoice)
    await sqlite_session.commit()
    await sqlite_session.refresh(offer)
    await sqlite_session.refresh(invoice)

    async def fake_download(_session, doc_id: int):
        return b"%PDF-1.4", f"document-{doc_id}.pdf"

    sent_messages = []

    def fake_send(message):
        sent_messages.append(message)

    monkeypatch.setattr("services.mail_smtp_service.DocumentService.get_download_stream", fake_download)
    monkeypatch.setattr(MailSmtpService, "send_message", fake_send)

    email_row = await MailSmtpService.send_order_email(
        sqlite_session,
        order_id=order.id,
        to_email="client@example.com",
        subject="Коммерческое предложение",
        body_text="Здравствуйте, документы во вложении.",
        document_ids=[offer.id, invoice.id],
    )

    assert email_row.status == "sent"
    assert len(email_row.attachments or []) == 2
    assert sent_messages

    refreshed_order = await sqlite_session.get(Order, order.id)
    assert refreshed_order.proposal_status == "sent"
    assert refreshed_order.proposal_sent_at is not None

    persisted_email = (await sqlite_session.execute(select(OutgoingEmail).where(OutgoingEmail.id == email_row.id))).scalar_one()
    assert persisted_email.recipient_email == "client@example.com"
    assert persisted_email.attachments[0]["mime_type"] == "application/pdf"


@pytest.mark.asyncio
async def test_send_order_email_without_offer_keeps_proposal_status(sqlite_session, monkeypatch):
    monkeypatch.setattr(settings, "MAIL_SMTP_USERNAME", "a@mvn.by")
    monkeypatch.setattr(settings, "MAIL_SMTP_PASSWORD", "super-secret")
    monkeypatch.setattr(settings, "MAIL_FROM_EMAIL", "a@mvn.by")

    customer = Customer(name="ООО Клиент", phone="+375291111111", type="company", email="client@example.com")
    sqlite_session.add(customer)
    await sqlite_session.commit()
    await sqlite_session.refresh(customer)

    order = Order(customer_id=customer.id, status="negotiation", proposal_status="draft")
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    invoice = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="СЧ-2026-002",
        google_file_id="invoice-file",
        google_edit_url="https://docs.example/invoice",
    )
    sqlite_session.add(invoice)
    await sqlite_session.commit()
    await sqlite_session.refresh(invoice)

    async def fake_download(_session, doc_id: int):
        return b"%PDF-1.4", f"document-{doc_id}.pdf"

    monkeypatch.setattr("services.mail_smtp_service.DocumentService.get_download_stream", fake_download)
    monkeypatch.setattr(MailSmtpService, "send_message", lambda _message: None)

    await MailSmtpService.send_order_email(
        sqlite_session,
        order_id=order.id,
        to_email="client@example.com",
        subject="Счет",
        body_text="Здравствуйте, счет во вложении.",
        document_ids=[invoice.id],
    )

    refreshed_order = await sqlite_session.get(Order, order.id)
    assert refreshed_order.proposal_status == "draft"
    assert refreshed_order.proposal_sent_at is None
