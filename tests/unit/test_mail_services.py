from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.config import settings
from models import BankReceipt, Customer, Order, OrderServiceLink, Payment, PaymentCurrency
from services.bank_email_parser_service import BankEmailParserService
from services.bank_receipt_service import BankReceiptService
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
async def test_bank_receipt_review_notification_goes_to_admins(sqlite_session, monkeypatch):
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

    sent_count = await NotificationService.notify_admins_bank_receipts_requires_review(
        sqlite_session,
        [receipt.id, matched.id],
    )

    assert sent_count == 2
    assert [item[0] for item in sent] == [101, 202]
    assert "Новые поступления требуют проверки: 1" in sent[0][1]
    assert "ООО Тест" in sent[0][1]
    assert "#50" in sent[0][1]
    assert "Уже разнесено" not in sent[0][1]


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
