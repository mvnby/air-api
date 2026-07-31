import pytest

from models import Customer, Order, OrderDocument, OrderProductLink, OrderServiceLink, Product
from services.order_email_template_service import OrderEmailTemplateService


@pytest.mark.asyncio
async def test_invoice_template_uses_order_scenario_and_reports_missing_requisites(db):
    customer = Customer(
        tenant_id=1,
        name="ООО Тест",
        full_legal_name="Общество с ограниченной ответственностью «Тест»",
        phone="+375291111111",
        email="client@example.com",
        type="company",
        inn="123456789",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=customer.id,
        status="negotiation",
        workflow_type="maintenance",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    invoice = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="СЧ-001",
        google_file_id="invoice",
        google_edit_url="https://docs.example/invoice",
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    result = await OrderEmailTemplateService.compose(
        db,
        order_id=order.id,
        document_ids=[invoice.id],
        template_key="auto",
    )

    assert result["template_key"] == "invoice"
    assert result["subject"] == "Счёт на техническое обслуживание кондиционеров"
    assert "Направляем счёт на техническое обслуживание кондиционеров." in result["body_text"]
    missing_keys = {item["key"] for item in result["missing_requisites"]}
    assert {"legal_address", "bank_name", "bic", "iban", "signer_name"} <= missing_keys
    assert "email" not in missing_keys
    assert "phone" not in missing_keys


@pytest.mark.asyncio
async def test_requisites_template_lists_only_missing_customer_fields(db):
    customer = Customer(
        tenant_id=1,
        name="ООО Клиент",
        full_legal_name="Общество с ограниченной ответственностью «Клиент»",
        phone="+375292222222",
        email="client@example.com",
        type="company",
        inn="987654321",
        legal_address="г. Витебск, ул. Ленина, 1",
        bank_name="Тест Банк",
        bic="TESTBY2X",
        iban="BY00TEST00000000000000000000",
        signer_name=None,
        signer_position="директора",
        acting_basis="Устава",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, workflow_type="service_work")
    db.add(order)
    await db.commit()
    await db.refresh(order)

    result = await OrderEmailTemplateService.compose(
        db,
        order_id=order.id,
        document_ids=[],
        template_key="request_requisites",
    )

    assert result["document_ids"] == []
    assert [item["key"] for item in result["missing_requisites"]] == ["signer_name"]
    assert "- ФИО подписанта." in result["body_text"]
    assert "юридический адрес" not in result["body_text"]


@pytest.mark.asyncio
async def test_documents_template_describes_multiple_attachments(db):
    customer = Customer(tenant_id=1, name="Клиент", phone="+375293333333", type="individual")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, workflow_type="sales_installation")
    db.add(order)
    await db.commit()
    await db.refresh(order)
    product = Product(title="Кондиционер", slug="email-template-product", price=1000)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=1000))
    await db.commit()

    invoice = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="СЧ-002",
        google_file_id="invoice",
        google_edit_url="https://docs.example/invoice",
    )
    contract = OrderDocument(
        order_id=order.id,
        doc_type="contract",
        number="Д-002",
        google_file_id="contract",
        google_edit_url="https://docs.example/contract",
    )
    db.add(invoice)
    db.add(contract)
    await db.commit()
    await db.refresh(invoice)
    await db.refresh(contract)

    result = await OrderEmailTemplateService.compose(
        db,
        order_id=order.id,
        document_ids=[invoice.id, contract.id],
        template_key="auto",
    )

    assert result["template_key"] == "documents"
    assert result["subject"] == "Счёт и договор на поставку кондиционеров"
    assert "Документы приложены к письму." in result["body_text"]


@pytest.mark.asyncio
async def test_signer_template_and_diagnostic_scenario_are_adaptive(db):
    customer = Customer(
        tenant_id=1,
        name="ООО Диагностика",
        phone="+375294444444",
        email="client@example.com",
        type="company",
        signer_name=None,
        signer_position="",
        acting_basis="",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, workflow_type="repair")
    db.add(order)
    await db.commit()
    await db.refresh(order)
    db.add(
        OrderServiceLink(
            order_id=order.id,
            title="Диагностика неисправности кондиционера",
            quantity=1,
            price=100,
        )
    )
    await db.commit()
    defect_act = OrderDocument(
        order_id=order.id,
        doc_type="defect_act",
        number="ДА-001",
        google_file_id="defect-act",
        google_edit_url="https://docs.example/defect-act",
    )
    db.add(defect_act)
    await db.commit()
    await db.refresh(defect_act)

    signer_request = await OrderEmailTemplateService.compose(
        db,
        order_id=order.id,
        document_ids=[],
        template_key="request_signer",
    )
    diagnostic_email = await OrderEmailTemplateService.compose(
        db,
        order_id=order.id,
        document_ids=[defect_act.id],
        template_key="auto",
    )

    assert "ФИО подписанта" in signer_request["body_text"]
    assert "должность подписанта" in signer_request["body_text"]
    assert "основание полномочий подписанта" in signer_request["body_text"]
    assert "юридический адрес" not in signer_request["body_text"]
    assert diagnostic_email["subject"] == "Дефектный акт на диагностику оборудования"
