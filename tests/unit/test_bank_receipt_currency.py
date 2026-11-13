"""Bank allocations use the receipt currency and the order's saved fixed price."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

from models import BankReceipt, Customer, Order, OrderServiceLink, Payment, PaymentCurrency
from services.bank_receipt_allocation_service import BankReceiptAllocationService
from services.bank_receipt_service import BankReceiptService


@pytest.fixture
async def currency_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        customer = Customer(tenant_id=1, name="Currency payer", phone="000", inn="123456789")
        session.add(customer)
        await session.commit()
        yield session, customer
    await engine.dispose()


async def make_order(session, customer, *, byn=300, currency=PaymentCurrency.USD, target=100):
    order = Order(
        tenant_id=1, storefront_id=1, customer_id=customer.id, status="execution",
        target_currency=currency, target_currency_amount=target,
    )
    session.add(order)
    await session.flush()
    session.add(OrderServiceLink(order_id=order.id, title="Service", quantity=1, price=byn, cost=0))
    await session.commit()
    return order


async def make_receipt(session, customer, *, amount=100, currency=PaymentCurrency.USD):
    receipt = BankReceipt(
        status="new", operation_type="incoming_funds", sender_email="bank@example.test",
        subject="Currency payment", fingerprint=f"currency-{amount}-{currency}",
        received_at=datetime(2026, 11, 1), amount=amount, currency=currency,
        payer_name=customer.name, payer_unp=customer.inn, payment_purpose="Service payment", raw_body="test",
    )
    session.add(receipt)
    await session.commit()
    return receipt


@pytest.mark.asyncio
@pytest.mark.parametrize("target_currency,target_amount", [
    (None, None), (PaymentCurrency.EUR, 100), (PaymentCurrency.USD, None),
    (PaymentCurrency.USD, 0), (PaymentCurrency.USD, -100),
])
async def test_foreign_receipt_cannot_match_or_allocate_incompatible_order(
    currency_session, target_currency, target_amount,
):
    session, customer = currency_session
    order = await make_order(session, customer, byn=100, currency=target_currency, target=target_amount)
    receipt = await make_receipt(session, customer)

    await BankReceiptService.match_receipt(session, receipt)
    await session.commit()
    assert receipt.status == "requires_review"
    assert not (await session.execute(select(Payment))).scalars().all()
    detail = await BankReceiptAllocationService.get_detail(session, receipt_id=receipt.id)
    assert detail["orders"] == []
    with pytest.raises(ValueError, match="currency"):
        await BankReceiptAllocationService.replace(
            session, receipt_id=receipt.id, allocations=[{"order_id": order.id, "amount": 100}],
        )
    assert not (await session.execute(select(Payment))).scalars().all()


@pytest.mark.asyncio
@pytest.mark.parametrize("currency,amount", [(PaymentCurrency.USD, 100), (PaymentCurrency.BYN, 300)])
async def test_receipt_settles_saved_target_price(currency_session, currency, amount):
    session, customer = currency_session
    order = await make_order(session, customer)
    receipt = await make_receipt(session, customer, amount=amount, currency=currency)

    await BankReceiptService.match_receipt(session, receipt)
    await session.commit()
    await session.refresh(order)
    payment = (await session.execute(select(Payment))).scalar_one()
    assert receipt.status == "matched"
    assert payment.currency == currency
    assert payment.amount == amount
    assert order.total_payments == pytest.approx(300)
    assert order.target_currency_payments == pytest.approx(100)
    assert order.balance_due == 0
    assert order.is_paid


@pytest.mark.asyncio
async def test_foreign_manual_attach_caps_allocation_in_receipt_currency(currency_session):
    session, customer = currency_session
    order = await make_order(session, customer)
    receipt = await make_receipt(session, customer, amount=150)

    await BankReceiptService.attach_receipt_to_order(session, receipt_id=receipt.id, order_id=order.id)
    payment = (await session.execute(select(Payment))).scalar_one()
    detail = await BankReceiptAllocationService.get_detail(session, receipt_id=receipt.id)
    assert payment.amount == 100
    assert payment.currency == PaymentCurrency.USD
    assert receipt.status == "partially_allocated"
    assert detail["unallocated_amount"] == 50
    assert detail["orders"][0]["balance_due_before_receipt"] == 100
    assert order.balance_due == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("manual", [False, True])
async def test_group_receipt_uses_each_orders_saved_target_price(currency_session, manual):
    session, customer = currency_session
    first = await make_order(session, customer, byn=300, target=50)
    second = await make_order(session, customer, byn=300, target=100)
    incompatible = await make_order(session, customer, byn=150, currency=None, target=None)
    receipt = await make_receipt(session, customer, amount=150)

    if manual:
        await BankReceiptService.attach_receipt_to_order_group(
            session, receipt_id=receipt.id, order_ids=[first.id, second.id],
        )
    else:
        await BankReceiptService.match_receipt(session, receipt)
        await session.commit()
        group = receipt.match_meta["group_match"]
        assert group["total_balance_due"] == 150
        assert {item["total_amount"] for item in group["orders"]} == {50, 100}
    payments = (await session.execute(select(Payment).order_by(Payment.amount))).scalars().all()
    assert [(payment.order_id, payment.amount) for payment in payments] == [(first.id, 50), (second.id, 100)]
    assert receipt.status == "matched"
    for order in (first, second):
        await session.refresh(order)
        assert order.balance_due == 0
        assert order.total_payments == 300
    assert not any(payment.order_id == incompatible.id for payment in payments)


@pytest.mark.asyncio
async def test_partial_reallocation_and_detail_preserve_mixed_currency_payments(currency_session):
    session, customer = currency_session
    first = await make_order(session, customer)
    second = await make_order(session, customer, byn=600)
    session.add(Payment(order_id=first.id, amount=60, currency=PaymentCurrency.BYN))
    await session.commit()
    receipt = await make_receipt(session, customer, amount=150)

    await BankReceiptAllocationService.replace(
        session, receipt_id=receipt.id, allocations=[{"order_id": first.id, "amount": 40}],
    )
    detail = await BankReceiptAllocationService.get_detail(session, receipt_id=receipt.id)
    row = next(item for item in detail["orders"] if item["order_id"] == first.id)
    assert row["total_amount"] == 100
    assert row["total_payments"] == 60
    assert row["current_allocation"] == 40
    assert row["balance_due_before_receipt"] == 80
    assert row["resulting_balance_due"] == 40
    assert first.total_payments == 180
    assert first.balance_due == 120

    with pytest.raises(ValueError, match="exceeds its debt"):
        await BankReceiptAllocationService.replace(
            session, receipt_id=receipt.id, allocations=[{"order_id": first.id, "amount": 90}],
        )
    await BankReceiptAllocationService.replace(
        session, receipt_id=receipt.id,
        allocations=[{"order_id": first.id, "amount": 80}, {"order_id": second.id, "amount": 70}],
    )
    await session.refresh(first)
    await session.refresh(second)
    assert first.total_payments == 300
    assert first.balance_due == 0
    assert second.total_payments == 420
    assert second.balance_due == 180
    assert receipt.status == "matched"

    await BankReceiptAllocationService.replace(session, receipt_id=receipt.id, allocations=[])
    await session.refresh(first)
    await session.refresh(second)
    assert first.total_payments == 60
    assert first.balance_due == 240
    assert second.total_payments == 0
    assert second.balance_due == 600


@pytest.mark.asyncio
async def test_incompatible_historical_allocation_can_be_cleared(currency_session):
    session, customer = currency_session
    order = await make_order(session, customer, byn=100, currency=None, target=None)
    receipt = await make_receipt(session, customer)
    payment = Payment(order_id=order.id, bank_receipt_id=receipt.id, amount=100, currency=PaymentCurrency.USD)
    session.add(payment)
    await session.flush()
    receipt.status = "matched"
    receipt.matched_order_id = order.id
    receipt.matched_payment_id = payment.id
    await session.commit()

    detail = await BankReceiptAllocationService.get_detail(session, receipt_id=receipt.id)
    assert detail["allocated_amount"] == 100
    assert detail["orders"] == []

    await BankReceiptAllocationService.replace(session, receipt_id=receipt.id, allocations=[])
    assert not (await session.execute(select(Payment))).scalars().all()
    assert receipt.status == "requires_review"
    assert receipt.matched_payment_id is None
    assert receipt.matched_order_id is None
    await session.refresh(order)
    assert order.balance_due == 100
