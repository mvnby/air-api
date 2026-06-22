from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import Customer, CustomerBranch, CustomerContract, DocumentTemplate, Order, OrderDocument, OrderProductLink, OrderProposal, OrderServiceLink, Product, Service
from services.document_service import DocumentService
from services.documents.factory import DocumentFactory
from services.documents.standard import ActStrategy, DefectActStrategy


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
async def test_base_document_placeholders_support_offer(sqlite_session):
    customer = Customer(name="Offer Customer", phone="+375291111111")
    order = Order(customer=customer, total_amount=120)
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    offer = OrderDocument(
        order_id=order.id,
        doc_type="offer",
        number="КП-2026-003",
        date=datetime(2026, 5, 3),
        google_file_id="offer-c",
        google_edit_url="https://example.com/offer-c",
    )
    sqlite_session.add(offer)
    await sqlite_session.commit()
    await sqlite_session.refresh(offer)

    resolved_document, resolved_customer_contract = await DocumentService._resolve_base_document(
        sqlite_session,
        order_id=order.id,
        doc_type="act",
        base_document_id=offer.id,
    )
    assert resolved_document.id == offer.id
    assert resolved_customer_contract is None

    strategy = ActStrategy(sqlite_session, order.id)
    await strategy.fetch_order()
    replacements = await strategy._prepare_base_variables(
        doc_number="А-2026-001",
        doc_type="act",
        document_date=datetime(2026, 5, 4),
        base_document=offer,
    )

    assert replacements["{{base_document_type}}"] == "КП"
    assert replacements["{{base_document_number}}"] == "КП-2026-003"
    assert replacements["{{base_document_date}}"] == "03.05.2026"
    assert replacements["{{offer_number}}"] == "КП-2026-003"
    assert replacements["{{offer_date}}"] == "03.05.2026"


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
async def test_act_scope_filters_services_and_overrides_object(sqlite_session):
    customer = Customer(name="Scoped Act", phone="+375291111111", type="company")
    branch = CustomerBranch(customer=customer, name="Объект Полоцк", delivery_address="Полоцк, Скорины 8А")
    order = Order(customer=customer, customer_branch=branch, delivery_address="Витебск, старый адрес")
    proposal = OrderProposal(order=order, name="Основное", is_selected=True)
    service_a = Service(title="Монтаж", slug="scope-install", base_price=300)
    service_b = Service(title="Демонтаж", slug="scope-dismantle", base_price=150)
    sqlite_session.add_all([customer, branch, order, proposal, service_a, service_b])
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    await sqlite_session.refresh(proposal)
    await sqlite_session.refresh(service_a)
    await sqlite_session.refresh(service_b)

    link_a = OrderServiceLink(
        order_id=order.id,
        proposal_id=proposal.id,
        service_id=service_a.id,
        quantity=1,
        price=300,
        cost=100,
    )
    link_b = OrderServiceLink(
        order_id=order.id,
        proposal_id=proposal.id,
        service_id=service_b.id,
        quantity=2,
        price=150,
        cost=50,
    )
    sqlite_session.add_all([link_a, link_b])
    await sqlite_session.commit()
    await sqlite_session.refresh(link_b)

    strategy = ActStrategy(sqlite_session, order.id)
    await strategy.fetch_order()
    DocumentService._apply_proposal_lines(strategy.order, proposal.id)
    scope = await DocumentService._build_document_scope(
        sqlite_session,
        strategy.order,
        scope_customer_branch_id=branch.id,
        scope_title=None,
        scope_address=None,
        scope_service_line_ids=[link_b.id],
        scope_service_line_quantities=[{"service_line_id": link_b.id, "quantity": 1}],
        scope_product_line_ids=None,
    )
    DocumentService._apply_document_scope(strategy.order, scope)
    replacements = await strategy._prepare_base_variables(
        doc_number="А-2026-100",
        doc_type="act",
        document_date=datetime(2026, 6, 22),
    )
    table_rows = strategy._prepare_table_data()

    assert replacements["{{object_name}}"] == "Объект Полоцк"
    assert replacements["{{object_address}}"] == "Полоцк, Скорины 8А"
    assert replacements["{{total_amount}}"] == "150.00"
    assert table_rows[0][1] == "Демонтаж"
    assert table_rows[0][3] == "1"
    assert table_rows[-1][-1] == "150.00"


@pytest.mark.asyncio
async def test_act_scope_rejects_service_line_from_another_order(sqlite_session):
    customer = Customer(name="Scope Guard", phone="+375291111111")
    order = Order(customer=customer)
    other_order = Order(customer=customer)
    service = Service(title="Монтаж guard", slug="scope-guard-install", base_price=300)
    sqlite_session.add_all([customer, order, other_order, service])
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    await sqlite_session.refresh(other_order)
    await sqlite_session.refresh(service)

    own_link = OrderServiceLink(order_id=order.id, service_id=service.id, quantity=1, price=300, cost=100)
    foreign_link = OrderServiceLink(order_id=other_order.id, service_id=service.id, quantity=1, price=300, cost=100)
    sqlite_session.add_all([own_link, foreign_link])
    await sqlite_session.commit()
    await sqlite_session.refresh(foreign_link)

    strategy = ActStrategy(sqlite_session, order.id)
    await strategy.fetch_order()
    scope = await DocumentService._build_document_scope(
        sqlite_session,
        strategy.order,
        scope_customer_branch_id=None,
        scope_title=None,
        scope_address=None,
        scope_service_line_ids=[foreign_link.id],
        scope_service_line_quantities=None,
        scope_product_line_ids=None,
    )

    with pytest.raises(ValueError, match="услуг"):
        DocumentService._apply_document_scope(strategy.order, scope)


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


@pytest.mark.asyncio
async def test_repair_order_existing_document_types_prepare_replacements(sqlite_session):
    customer = Customer(name="Repair Docs", phone="+375291111111")
    order = Order(
        customer=customer,
        workflow_type="repair",
        title="Кондиционер",
        total_amount=120,
        additional_conditions="1. Диагностика согласована клиентом.",
        technical_meta={
            "repair": {
                "repair_status": "scheduled",
                "customer_approval_status": "pending",
                "parts_status": "awaiting",
            },
        },
    )
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    for doc_type in ("contract", "invoice", "retail_receipt", "service_act", "offer", "act", "defect_act"):
        strategy = DocumentFactory.get_strategy(doc_type, sqlite_session, order.id)
        await strategy.fetch_order()
        replacements = await strategy._prepare_base_variables(
            doc_number=f"{DocumentService.DOC_NUMBER_PREFIXES[doc_type]}-2026-001",
            doc_type=doc_type,
            document_date=datetime(2026, 5, 20),
        )
        strategy._add_specific_replacements(replacements)

        assert replacements["{{client_name}}"] == "Repair Docs"
        assert replacements["{{additional_conditions}}"] == "Диагностика согласована клиентом."
        if doc_type == "defect_act":
            assert replacements["{{repair_status}}"] == "scheduled"
            assert replacements["{{customer_approval_status}}"] == "pending"
            assert replacements["{{parts_status}}"] == "awaiting"


@pytest.mark.asyncio
async def test_b2c_retail_receipt_placeholders_use_offer_basis_and_order_lines(sqlite_session):
    customer = Customer(name="Private Customer", phone="+375291111111")
    product = Product(title="Кондиционер Test 09", slug="test-09", price=1500, cost=1000)
    service = Service(title="Стандартный монтаж", slug="standard-install", base_price=500)
    order = Order(
        customer=customer,
        delivery_address="г. Витебск, адрес установки",
        total_amount=2000,
    )
    sqlite_session.add_all([customer, product, service, order])
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    sqlite_session.add_all(
        [
            OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=1500, cost=1000),
            OrderServiceLink(order_id=order.id, service_id=service.id, quantity=1, price=500, cost=0),
        ]
    )
    await sqlite_session.commit()

    strategy = DocumentFactory.get_strategy("retail_receipt", sqlite_session, order.id)
    await strategy.fetch_order()
    replacements = await strategy._prepare_base_variables(
        doc_number="ТЧ-2026-001",
        doc_type="retail_receipt",
        document_date=datetime(2026, 6, 5),
    )
    strategy._add_specific_replacements(replacements)
    strategy._append_placeholder_aliases(replacements)

    assert replacements["{{base_document_type}}"] == "Публичная оферта"
    assert replacements["{{base_document_number}}"] == "https://mvn.by/offer/"
    assert replacements["{{offer_url}}"] == "https://mvn.by/offer/"
    assert replacements["{{client_name}}"] == "Private Customer"
    assert replacements["{{object_address}}"] == "г. Витебск, адрес установки"
    assert replacements["{{receipt_product_lines}}"] == "Кондиционер Test 09"
    assert replacements["{{receipt_product_qty}}"] == "1"
    assert replacements["{{receipt_product_price}}"] == "1500,00"
    assert replacements["{{receipt_product_total}}"] == "1500,00"
    assert replacements["{{receipt_service_lines}}"] == "Стандартный монтаж"
    assert replacements["{{receipt_service_total}}"] == "500,00"
    assert replacements["{{receipt_total}}"] == "2000,00"
    assert replacements["{{RECEIPT_TOTAL}}"] == "2000,00"


@pytest.mark.asyncio
async def test_b2c_service_act_placeholders_support_service_only_order(sqlite_session):
    customer = Customer(name="Service Customer", phone="+375292222222")
    service = Service(title="Обслуживание кондиционера", slug="maintenance", base_price=180)
    order = Order(
        customer=customer,
        delivery_address="г. Витебск, сервисный адрес",
        total_amount=180,
        title="Обслуживание",
    )
    sqlite_session.add_all([customer, service, order])
    await sqlite_session.commit()
    await sqlite_session.refresh(order)
    sqlite_session.add(OrderServiceLink(order_id=order.id, service_id=service.id, quantity=1, price=180, cost=0))
    await sqlite_session.commit()

    strategy = DocumentFactory.get_strategy("service_act", sqlite_session, order.id)
    await strategy.fetch_order()
    replacements = await strategy._prepare_base_variables(
        doc_number="ЗА-2026-001",
        doc_type="service_act",
        document_date=datetime(2026, 6, 6),
    )
    strategy._add_specific_replacements(replacements)

    assert replacements["{{base_document_type}}"] == "Публичная оферта"
    assert replacements["{{equipment_primary}}"] == "кондиционер / сплит-система"
    assert replacements["{{service_act_lines}}"] == "Обслуживание кондиционера"
    assert replacements["{{service_act_total}}"] == "180,00"
    assert replacements["{{date_text}}"] == "06 июня 2026 г."


@pytest.mark.asyncio
async def test_defect_act_canonical_repair_placeholders_from_repair_meta(sqlite_session):
    customer = Customer(name="Repair Canonical", phone="+375291111111")
    order = Order(
        customer=customer,
        title="Кондиционер",
        additional_conditions="1. Работы выполнять после согласования.\n- Доступ предоставить с 9:00.",
        technical_meta={
            "repair": {
                "customer_complaint": "Не охлаждает",
                "diagnostic_result": "Диагностика выявила утечку хладагента.",
                "repair_recommendation": "Устранить утечку и дозаправить контур.",
                "repair_possible": "Да",
                "repair_status": "awaiting_parts",
                "customer_approval_status": "approved",
                "customer_approval_note": "Клиент согласовал ремонт по телефону.",
                "parts_status": "awaiting",
                "parts_note": "Ожидается поставка датчика температуры.",
                "repair_completion_note": "Ремонт будет завершен после поставки запчастей.",
                "refrigerant_type": "R32",
                "refrigerant_amount": "0,45 кг",
                "refrigerant_pricing_mode": "по фактической массе",
                "repair_not_viable": "Нет",
                "repair_not_viable_reason": "Оснований для списания не выявлено.",
            },
        },
    )
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    strategy = DefectActStrategy(sqlite_session, order.id)
    await strategy.fetch_order()
    replacements = await strategy._prepare_base_variables(
        doc_number="ДА-2026-001",
        doc_type="defect_act",
        document_date=datetime(2026, 5, 14),
    )
    strategy._add_specific_replacements(replacements)

    assert replacements["{{customer_complaint}}"] == "Не охлаждает"
    assert replacements["{{diagnostic_result}}"] == "Диагностика выявила утечку хладагента."
    assert replacements["{{measurement_result}}"] == "Диагностика выявила утечку хладагента."
    assert replacements["{{repair_recommendation}}"] == "Устранить утечку и дозаправить контур."
    assert replacements["{{technical_conclusion}}"] == "Устранить утечку и дозаправить контур."
    assert replacements["{{recommended_decision}}"] == "Устранить утечку и дозаправить контур."
    assert replacements["{{repair_possible}}"] == "Да"
    assert replacements["{{repair_feasibility}}"] == "Да"
    assert replacements["{{repair_status}}"] == "awaiting_parts"
    assert replacements["{{customer_approval_status}}"] == "approved"
    assert replacements["{{customer_approval_note}}"] == "Клиент согласовал ремонт по телефону."
    assert replacements["{{parts_status}}"] == "awaiting"
    assert replacements["{{parts_note}}"] == "Ожидается поставка датчика температуры."
    assert replacements["{{repair_completion_note}}"] == "Ремонт будет завершен после поставки запчастей."
    assert replacements["{{refrigerant_type}}"] == "R32"
    assert replacements["{{refrigerant_amount}}"] == "0,45 кг"
    assert replacements["{{refrigerant_pricing_mode}}"] == "по фактической массе"
    assert replacements["{{repair_not_viable}}"] == "Нет"
    assert replacements["{{repair_not_viable_reason}}"] == "Оснований для списания не выявлено."
    assert replacements["{{additional_conditions}}"] == (
        "Работы выполнять после согласования.\nДоступ предоставить с 9:00."
    )


@pytest.mark.asyncio
async def test_defect_act_legacy_repair_aliases_feed_canonical_placeholders(sqlite_session):
    customer = Customer(name="Repair Legacy", phone="+375291111111")
    order = Order(
        customer=customer,
        title="Кондиционер",
        technical_meta={
            "repair": {
                "complaint_official": "Отсутствие охлаждения в рабочем режиме.",
                "measurement_result": "При осмотре выявлены признаки утечки.",
                "technical_conclusion": "Эксплуатация без ремонта не рекомендуется.",
                "repair_feasibility": "Ремонт экономически нецелесообразен.",
            },
        },
    )
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    strategy = DefectActStrategy(sqlite_session, order.id)
    await strategy.fetch_order()
    replacements = await strategy._prepare_base_variables(
        doc_number="ДА-2026-002",
        doc_type="defect_act",
        document_date=datetime(2026, 5, 15),
    )
    strategy._add_specific_replacements(replacements)

    assert replacements["{{customer_complaint}}"] == "Отсутствие охлаждения в рабочем режиме."
    assert replacements["{{diagnostic_result}}"] == "При осмотре выявлены признаки утечки."
    assert replacements["{{measurement_result}}"] == "При осмотре выявлены признаки утечки."
    assert replacements["{{repair_recommendation}}"] == "Эксплуатация без ремонта не рекомендуется."
    assert replacements["{{technical_conclusion}}"] == "Эксплуатация без ремонта не рекомендуется."
    assert replacements["{{repair_feasibility}}"] == "Ремонт экономически нецелесообразен."
    assert replacements["{{repair_possible}}"] == "_________________"
    assert replacements["{{repair_status}}"] == "_________________"
    assert replacements["{{customer_approval_status}}"] == "_________________"
    assert replacements["{{customer_approval_note}}"] == "_________________"
    assert replacements["{{parts_status}}"] == "_________________"
    assert replacements["{{parts_note}}"] == "_________________"
    assert replacements["{{repair_completion_note}}"] == "_________________"
    assert replacements["{{repair_not_viable}}"] == "Ремонт экономически нецелесообразен."
    assert replacements["{{repair_not_viable_reason}}"] == "Ремонт экономически нецелесообразен."


@pytest.mark.asyncio
async def test_defect_act_legacy_conclusion_placeholder_prefers_legacy_value(sqlite_session):
    customer = Customer(name="Repair Mixed", phone="+375291111111")
    order = Order(
        customer=customer,
        title="Кондиционер",
        technical_meta={
            "repair": {
                "technical_conclusion": "Компрессор неисправен, эксплуатация запрещена.",
                "recommended_decision": "Вывести оборудование из эксплуатации.",
                "repair_recommendation": "Заменить компрессор при наличии экономической целесообразности.",
            },
        },
    )
    sqlite_session.add(order)
    await sqlite_session.commit()
    await sqlite_session.refresh(order)

    strategy = DefectActStrategy(sqlite_session, order.id)
    await strategy.fetch_order()
    replacements = await strategy._prepare_base_variables(
        doc_number="ДА-2026-003",
        doc_type="defect_act",
        document_date=datetime(2026, 5, 16),
    )
    strategy._add_specific_replacements(replacements)

    assert replacements["{{technical_conclusion}}"] == "Компрессор неисправен, эксплуатация запрещена."
    assert replacements["{{recommended_decision}}"] == "Вывести оборудование из эксплуатации."
    assert replacements["{{repair_recommendation}}"] == (
        "Заменить компрессор при наличии экономической целесообразности."
    )
