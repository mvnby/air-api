from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.config import settings
from models import BankReceipt, Customer, Order, OrderServiceLink, Payment, PaymentCurrency
from services.bank_email_parser_service import BankEmailParserService
from services.bank_receipt_service import BankReceiptService
from services.mail_smtp_service import MailAttachment, MailSmtpService


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
