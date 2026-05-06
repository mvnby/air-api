from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import Customer, DocumentTemplate, GlobalConfig, Order, OrderDocument
from services.document_template_service import DocumentTemplateService


@pytest.fixture()
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'doc_templates.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_relevant_contract_templates_include_default_and_customer_specific(sqlite_session):
    customer = Customer(name="Банк", phone="+375291111111", type="company")
    other_customer = Customer(name="Другой клиент", phone="+375292222222", type="company")
    default_template = DocumentTemplate(
        name="Стандартный договор",
        doc_type="contract",
        google_template_id="default-contract",
        is_default=True,
        is_active=True,
        sort_order=0,
    )
    bank_template = DocumentTemplate(
        name="Форма банка",
        doc_type="contract",
        google_template_id="bank-contract",
        is_active=True,
        client_restricted=True,
        sort_order=10,
    )
    hidden_template = DocumentTemplate(
        name="Чужой договор",
        doc_type="contract",
        google_template_id="other-contract",
        is_active=True,
        client_restricted=True,
        sort_order=20,
    )
    bank_template.customers = [customer]
    hidden_template.customers = [other_customer]
    sqlite_session.add_all([customer, other_customer, default_template, bank_template, hidden_template])
    await sqlite_session.commit()

    items = await DocumentTemplateService.get_relevant_templates(sqlite_session, "contract", customer_id=customer.id)

    assert [item["id"] for item in items] == ["default-contract", "bank-contract"]


@pytest.mark.asyncio
async def test_act_template_is_selected_from_contract_template_link(sqlite_session):
    customer = Customer(name="Банк", phone="+375291111111", type="company")
    contract_template = DocumentTemplate(
        name="Форма банка",
        doc_type="contract",
        google_template_id="bank-contract",
        is_active=True,
    )
    act_template = DocumentTemplate(
        name="Акт банка",
        doc_type="act",
        google_template_id="bank-act",
        is_active=True,
    )
    default_act = DocumentTemplate(
        name="Стандартный акт",
        doc_type="act",
        google_template_id="default-act",
        is_active=True,
        is_default=True,
    )
    act_template.linked_contract_templates = [contract_template]
    order = Order(customer=customer, status="negotiation")
    sqlite_session.add_all([customer, contract_template, act_template, default_act, order])
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    await sqlite_session.refresh(contract_template)
    contract_doc = OrderDocument(
        order_id=order.id,
        document_template_id=contract_template.id,
        template_id=contract_template.google_template_id,
        doc_type="contract",
        number="D-1",
        google_file_id="doc",
        google_edit_url="https://example.com/doc",
    )
    sqlite_session.add(contract_doc)
    await sqlite_session.commit()

    resolved_id, google_id = await DocumentTemplateService.resolve_template_for_generation(
        sqlite_session,
        order_id=order.id,
        doc_type="act",
    )

    assert resolved_id == act_template.id
    assert google_id == "bank-act"


@pytest.mark.asyncio
async def test_legacy_contract_templates_are_returned_when_no_managed_rows(sqlite_session):
    sqlite_session.add(
        GlobalConfig(
            key="contract_templates",
            value='[{"id": "legacy-id", "name": "Старый договор", "document_role_type": "executor_customer"}]',
            description="legacy",
        )
    )
    await sqlite_session.commit()

    items = await DocumentTemplateService.get_relevant_templates(sqlite_session, "contract", customer_id=None)

    assert items[0]["id"] == "legacy-id"
    assert items[0]["document_template_id"] is None
    assert items[0]["document_role_type"] == "executor_customer"


@pytest.mark.asyncio
async def test_non_managed_document_type_uses_legacy_template_id(sqlite_session):
    resolved_id, google_id = await DocumentTemplateService.resolve_template_for_generation(
        sqlite_session,
        order_id=123,
        doc_type="offer",
        template_id="custom-offer",
    )

    assert resolved_id is None
    assert google_id == "custom-offer"


@pytest.mark.asyncio
async def test_act_template_can_be_selected_from_invoice_template_link(sqlite_session):
    customer = Customer(name="Белагробанк", phone="+375293333333", type="company")
    invoice_template = DocumentTemplate(
        name="Счет-договор банка",
        doc_type="invoice",
        google_template_id="bank-invoice",
        is_active=True,
    )
    act_template = DocumentTemplate(
        name="Акт к счету банка",
        doc_type="act",
        google_template_id="bank-invoice-act",
        is_active=True,
    )
    act_template.linked_contract_templates = [invoice_template]
    order = Order(customer=customer, status="negotiation")
    sqlite_session.add_all([customer, invoice_template, act_template, order])
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    await sqlite_session.refresh(invoice_template)
    sqlite_session.add(
        OrderDocument(
            order_id=order.id,
            document_template_id=invoice_template.id,
            template_id=invoice_template.google_template_id,
            doc_type="invoice",
            number="S-1",
            google_file_id="doc",
            google_edit_url="https://example.com/doc",
        )
    )
    await sqlite_session.commit()

    resolved_id, google_id = await DocumentTemplateService.resolve_template_for_generation(
        sqlite_session,
        order_id=order.id,
        doc_type="act",
    )

    assert resolved_id == act_template.id
    assert google_id == "bank-invoice-act"
