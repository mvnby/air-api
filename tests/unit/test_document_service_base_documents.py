from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import Customer, CustomerContract, DocumentTemplate, Order, OrderDocument
from services.document_service import DocumentService
from services.documents.standard import ActStrategy


@pytest.fixture()
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'doc_base.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_document_numbering_uses_prefix_and_year(sqlite_session):
    customer = Customer(name="Numbering", phone="+375291111111")
    order = Order(customer=customer)
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    sqlite_session.add_all(
        [
            OrderDocument(
                order_id=order.id,
                doc_type="contract",
                number="Д-2026-001",
                date=datetime(2026, 1, 10),
                google_file_id="contract-a",
                google_edit_url="https://example.com/contract-a",
            ),
            OrderDocument(
                order_id=order.id,
                doc_type="contract",
                number="Д-2025-999",
                date=datetime(2025, 12, 31),
                google_file_id="contract-old",
                google_edit_url="https://example.com/contract-old",
            ),
        ]
    )
    await sqlite_session.commit()

    assert await DocumentService._get_next_number(sqlite_session, "contract", datetime(2026, 5, 1)) == "Д-2026-002"
    assert await DocumentService._get_next_number(sqlite_session, "contract", datetime(2027, 1, 1)) == "Д-2027-001"


@pytest.mark.asyncio
async def test_resolve_base_document_requires_choice_when_multiple_exist(sqlite_session):
    customer = Customer(name="Base", phone="+375291111111")
    order = Order(customer=customer)
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    invoice_a = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="С-2026-001",
        date=datetime(2026, 5, 1),
        google_file_id="invoice-a",
        google_edit_url="https://example.com/a",
    )
    invoice_b = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="С-2026-002",
        date=datetime(2026, 5, 2),
        google_file_id="invoice-b",
        google_edit_url="https://example.com/b",
    )
    sqlite_session.add_all([invoice_a, invoice_b])
    await sqlite_session.commit()
    await sqlite_session.refresh(invoice_b)

    with pytest.raises(ValueError, match="основание"):
        await DocumentService._resolve_base_document(
            sqlite_session,
            order_id=order.id,
            doc_type="act",
            base_document_id=None,
        )

    resolved_document, resolved_customer_contract = await DocumentService._resolve_base_document(
        sqlite_session,
        order_id=order.id,
        doc_type="act",
        base_document_id=invoice_b.id,
    )
    assert resolved_document.id == invoice_b.id
    assert resolved_customer_contract is None


@pytest.mark.asyncio
async def test_base_document_placeholders_support_invoice(sqlite_session):
    customer = Customer(name="Invoice Customer", phone="+375291111111")
    order = Order(customer=customer, total_amount=120)
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    invoice = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="С-2026-003",
        date=datetime(2026, 5, 3),
        google_file_id="invoice-c",
        google_edit_url="https://example.com/c",
    )
    sqlite_session.add(invoice)
    await sqlite_session.commit()
    await sqlite_session.refresh(invoice)

    strategy = ActStrategy(sqlite_session, order.id)
    await strategy.fetch_order()
    replacements = await strategy._prepare_base_variables(
        doc_number="А-2026-001",
        doc_type="act",
        document_date=datetime(2026, 5, 4),
        base_document=invoice,
    )

    assert replacements["{{base_document_type}}"] == "Счет"
    assert replacements["{{base_document_number}}"] == "С-2026-003"
    assert replacements["{{base_document_date}}"] == "03.05.2026"
    assert replacements["{{invoice_number}}"] == "С-2026-003"
    assert replacements["{{invoice_date}}"] == "03.05.2026"
    assert replacements["{{INVOICE_NUMBER}}"] == "С-2026-003"
    assert replacements["{{INVOICE_DATE}}"] == "03.05.2026"


@pytest.mark.asyncio
async def test_current_invoice_placeholders_use_generated_number_and_uppercase_aliases(sqlite_session):
    customer = Customer(name="Invoice Self", phone="+375291111111")
    order = Order(customer=customer, total_amount=120)
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    strategy = ActStrategy(sqlite_session, order.id)
    await strategy.fetch_order()
    replacements = await strategy._prepare_base_variables(
        doc_number="С-2026-004",
        doc_type="invoice",
        document_date=datetime(2026, 6, 1),
    )

    assert replacements["{{invoice_number}}"] == "С-2026-004"
    assert replacements["{{invoice_date}}"] == "01.06.2026"
    assert replacements["{{INVOICE_NUMBER}}"] == "С-2026-004"
    assert replacements["{{INVOICE_DATE}}"] == "01.06.2026"
    assert replacements["{{DOC_NUMBER}}"] == "С-2026-004"


@pytest.mark.asyncio
async def test_base_document_type_uses_invoice_template_label(sqlite_session):
    customer = Customer(name="Invoice Label", phone="+375291111111")
    order = Order(customer=customer, total_amount=120)
    template = DocumentTemplate(
        name="Счет-договор",
        doc_type="invoice",
        google_template_id="invoice-template",
        base_document_type_label="Счет-договор",
    )
    sqlite_session.add_all([order, template])
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    await sqlite_session.refresh(template)

    invoice = OrderDocument(
        order_id=order.id,
        document_template_id=template.id,
        doc_type="invoice",
        number="С-2026-005",
        date=datetime(2026, 6, 1),
        google_file_id="invoice-d",
        google_edit_url="https://example.com/d",
    )
    sqlite_session.add(invoice)
    await sqlite_session.commit()
    await sqlite_session.refresh(invoice)

    strategy = ActStrategy(sqlite_session, order.id)
    await strategy.fetch_order()
    replacements = await strategy._prepare_base_variables(
        doc_number="А-2026-003",
        doc_type="act",
        document_date=datetime(2026, 6, 2),
        base_document=invoice,
    )

    assert replacements["{{base_document_type}}"] == "Счет-договор"
    assert replacements["{{BASE_DOCUMENT_TYPE}}"] == "Счет-договор"
    assert replacements["{{base_document_number}}"] == "С-2026-005"


@pytest.mark.asyncio
async def test_open_customer_contract_can_be_stable_base(sqlite_session):
    customer = Customer(name="Contract Customer", phone="+375291111111", type="company")
    contract = CustomerContract(
        customer=customer,
        number="ОД-2026-010",
        valid_from=datetime(2026, 1, 15),
        valid_until=datetime(2027, 1, 15),
        status="active",
    )
    order = Order(customer=customer, customer_contract=contract)
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    await sqlite_session.refresh(contract)

    base_document, base_customer_contract = await DocumentService._resolve_base_document(
        sqlite_session,
        order_id=order.id,
        doc_type="act",
        base_document_id=0,
    )

    assert base_document is None
    assert base_customer_contract.id == contract.id

    strategy = ActStrategy(sqlite_session, order.id)
    await strategy.fetch_order()
    replacements = await strategy._prepare_base_variables(
        doc_number="А-2026-002",
        doc_type="act",
        document_date=datetime(2026, 5, 5),
        base_customer_contract=base_customer_contract,
    )

    assert replacements["{{base_document_type}}"] == "Договор"
    assert replacements["{{base_document_number}}"] == "ОД-2026-010"
    assert replacements["{{base_document_date}}"] == "15.01.2026"
    assert replacements["{{contract_number}}"] == "ОД-2026-010"
