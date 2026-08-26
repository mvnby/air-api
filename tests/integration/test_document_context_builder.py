from datetime import date

import pytest

from models import (
    Customer,
    CustomerType,
    DocumentLegalEntity,
    Order,
    OrderDocument,
    OrderProductLink,
    OrderProposal,
    OrderServiceLink,
    OrderStatus,
    Product,
    Service,
    Tenant,
)
from models.tenancy import TenantScope
from modules.documents.application.context_builder import (
    DocumentContextBuilder,
    DocumentContextError,
    DocumentContextSelection,
)


async def _seed_order(db):
    customer = Customer(
        tenant_id=1,
        name="ООО Покупатель",
        full_legal_name="Общество с ограниченной ответственностью Покупатель",
        phone="+375291111111",
        email="buyer@example.test",
        inn="123456789",
        legal_address="г. Витебск, ул. Клиентская, 1",
        bank_name="Банк покупателя",
        iban="BY00TEST00000000000000000000",
        bic="TESTBY2X",
        signer_name="Иванов И.И.",
        type=CustomerType.company,
    )
    selected_product = Product(
        title="Кондиционер выбранный",
        slug="native-context-selected-product",
        price=1_000,
        specs={
            "country": "Китай",
            "logistics_components": [
                {
                    "title": "Внутренний блок",
                    "unit": "шт.",
                    "quantity_per_parent": 1,
                    "price_weight": 1,
                    "kind": "indoor",
                },
                {
                    "title": "Наружный блок",
                    "unit": "шт.",
                    "quantity_per_parent": 1,
                    "price_weight": 2,
                    "kind": "outdoor",
                },
            ],
        },
    )
    alternative_product = Product(
        title="Кондиционер альтернативный",
        slug="native-context-alternative-product",
        price=2_000,
    )
    installation = Service(
        title="Монтаж кондиционера",
        slug="native-context-installation",
        base_price=200,
    )
    issuer = DocumentLegalEntity(
        tenant_id=1,
        slug="mvn-documents",
        display_name="ООО Мастер Воздуха",
        legal_name="Общество с ограниченной ответственностью Мастер Воздуха",
        unp="390000000",
        is_default=True,
        is_vat_payer=False,
        requisites={
            "legal_address": "г. Витебск, ул. Продавца, 1",
            "iban": "BY00SELLER0000000000000000",
        },
    )
    db.add_all([customer, selected_product, alternative_product, installation, issuer])
    await db.flush()

    order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        title="Монтаж системы кондиционирования",
        delivery_address="г. Витебск, объект покупателя",
        total_amount=1_400,
        total_cost=900,
        margin=500,
    )
    db.add(order)
    await db.flush()
    selected = OrderProposal(
        order_id=order.id,
        name="Выбранный вариант",
        is_selected=True,
        sort_order=0,
    )
    alternative = OrderProposal(
        order_id=order.id,
        name="Альтернатива",
        is_selected=False,
        sort_order=1,
    )
    db.add_all([selected, alternative])
    await db.flush()
    db.add_all(
        [
            OrderProductLink(
                order_id=order.id,
                proposal_id=selected.id,
                product_id=selected_product.id,
                quantity=1,
                price=1_000,
                cost=700,
            ),
            OrderServiceLink(
                order_id=order.id,
                proposal_id=selected.id,
                service_id=installation.id,
                title=installation.title,
                quantity=2,
                price=200,
                cost=100,
            ),
            OrderProductLink(
                order_id=order.id,
                proposal_id=alternative.id,
                product_id=alternative_product.id,
                quantity=1,
                price=2_000,
                cost=1_300,
            ),
        ]
    )
    await db.commit()
    return order, issuer, selected, alternative


@pytest.mark.asyncio
async def test_context_snapshot_uses_selected_proposal_and_does_not_mutate_order(db):
    order, issuer, selected, _alternative = await _seed_order(db)

    snapshot = await DocumentContextBuilder.build(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        selection=DocumentContextSelection(
            order_id=order.id,
            legal_entity_id=issuer.id,
            document_type="invoice",
            issue_date=date(2026, 8, 26),
        ),
    )

    assert snapshot["schema_version"] == 1
    assert snapshot["meta"]["proposal_id"] == selected.id
    assert snapshot["meta"]["business_role"] == "payment_request"
    assert snapshot["values"]["seller.unp"] == "390000000"
    assert snapshot["values"]["customer.unp"] == "123456789"
    assert snapshot["values"]["totals.amount"] == "1400.00"
    assert [row["line.title"] for row in snapshot["table_rows"]["lines"]] == [
        "Кондиционер выбранный",
        "Монтаж кондиционера",
    ]
    assert snapshot["table_rows"]["lines"][1]["line.quantity"] == "2"

    await db.refresh(order)
    assert order.total_amount == 1_400


@pytest.mark.asyncio
async def test_act_prefers_contract_and_never_uses_payment_request_invoice(db):
    order, issuer, selected, _alternative = await _seed_order(db)
    payment_request = OrderDocument(
        tenant_id=1,
        legal_entity_id=issuer.id,
        order_id=order.id,
        proposal_id=selected.id,
        doc_type="invoice",
        business_role="payment_request",
        status="issued",
        internal_reference="doc_payment_request",
        official_series="СЧ-",
        official_period_key="2026",
        official_number="001",
        official_date=date(2026, 8, 20),
        number="legacy-payment-request",
        google_file_id=None,
        google_edit_url=None,
    )
    contract = OrderDocument(
        tenant_id=1,
        legal_entity_id=issuer.id,
        order_id=order.id,
        proposal_id=selected.id,
        doc_type="contract",
        status="issued",
        internal_reference="doc_contract",
        official_series="Д-",
        official_period_key="2026",
        official_number="007",
        official_date=date(2026, 8, 21),
        number="legacy-contract",
        google_file_id=None,
        google_edit_url=None,
    )
    db.add_all([payment_request, contract])
    await db.commit()

    snapshot = await DocumentContextBuilder.build(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        selection=DocumentContextSelection(
            order_id=order.id,
            legal_entity_id=issuer.id,
            document_type="act",
            issue_date=date(2026, 8, 26),
        ),
    )

    assert snapshot["meta"]["base_document_id"] == contract.id
    assert snapshot["values"]["basis.type"] == "Договор"
    assert snapshot["values"]["basis.number"] == "Д-007"
    assert snapshot["values"]["basis.date"] == "21.08.2026"

    with pytest.raises(DocumentContextError, match="не является основанием"):
        await DocumentContextBuilder.build(
            db,
            tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
            selection=DocumentContextSelection(
                order_id=order.id,
                legal_entity_id=issuer.id,
                document_type="act",
                issue_date=date(2026, 8, 26),
                base_document_id=payment_request.id,
            ),
        )


@pytest.mark.asyncio
async def test_legacy_invoice_without_explicit_offer_role_is_never_a_basis(db):
    order, issuer, selected, _alternative = await _seed_order(db)
    legacy_invoice = OrderDocument(
        order_id=order.id,
        proposal_id=selected.id,
        doc_type="invoice",
        business_role=None,
        status=None,
        number="legacy-invoice-42",
        google_file_id="legacy-google-file",
        google_edit_url="https://docs.google.test/legacy-invoice-42",
    )
    db.add(legacy_invoice)
    await db.commit()

    with pytest.raises(DocumentContextError, match="нужен договор"):
        await DocumentContextBuilder.build(
            db,
            tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
            selection=DocumentContextSelection(
                order_id=order.id,
                legal_entity_id=issuer.id,
                document_type="act",
                issue_date=date(2026, 8, 26),
            ),
        )

    with pytest.raises(DocumentContextError, match="не является основанием"):
        await DocumentContextBuilder.build(
            db,
            tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
            selection=DocumentContextSelection(
                order_id=order.id,
                legal_entity_id=issuer.id,
                document_type="act",
                issue_date=date(2026, 8, 26),
                base_document_id=legacy_invoice.id,
            ),
        )


@pytest.mark.asyncio
async def test_paper_waybill_uses_contract_and_only_expanded_product_rows(db):
    order, issuer, selected, _alternative = await _seed_order(db)
    contract = OrderDocument(
        tenant_id=1,
        legal_entity_id=issuer.id,
        order_id=order.id,
        proposal_id=selected.id,
        doc_type="contract",
        status="issued",
        internal_reference="doc_waybill_contract",
        official_series="Д-",
        official_period_key="2026",
        official_number="009",
        official_date=date(2026, 8, 21),
        number="legacy-waybill-contract",
        google_file_id=None,
        google_edit_url=None,
    )
    db.add(contract)
    await db.commit()

    snapshot = await DocumentContextBuilder.build(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        selection=DocumentContextSelection(
            order_id=order.id,
            legal_entity_id=issuer.id,
            document_type="tn2",
            issue_date=date(2026, 8, 26),
        ),
    )

    assert snapshot["meta"]["base_document_id"] == contract.id
    assert snapshot["values"]["basis.number"] == "Д-009"
    assert snapshot["values"]["totals.amount"] == "1000.00"
    assert snapshot["values"]["totals.quantity"] == "2"
    assert snapshot["values"]["transport.car_number"] == "—"
    assert snapshot["table_rows"]["lines"] == [
        {
            "line.number": "1",
            "line.title": "Внутренний блок",
            "line.kind": "product",
            "line.country": "Китай",
            "line.unit": "шт.",
            "line.quantity": "1",
            "line.unit_price": "333.33",
            "line.amount": "333.33",
            "line.vat_label": "без НДС",
            "line.seats": "1",
            "line.mass": "0.00",
            "line.note": "—",
        },
        {
            "line.number": "2",
            "line.title": "Наружный блок",
            "line.kind": "product",
            "line.country": "Китай",
            "line.unit": "шт.",
            "line.quantity": "1",
            "line.unit_price": "666.67",
            "line.amount": "666.67",
            "line.vat_label": "без НДС",
            "line.seats": "1",
            "line.mass": "0.00",
            "line.note": "—",
        },
    ]


@pytest.mark.asyncio
async def test_context_builder_rejects_cross_tenant_issuer(db):
    order, _issuer, _selected, _alternative = await _seed_order(db)
    other_tenant = Tenant(
        slug="other-documents-tenant",
        display_name="Чужой арендатор",
    )
    db.add(other_tenant)
    await db.flush()
    other_issuer = DocumentLegalEntity(
        tenant_id=other_tenant.id,
        slug="other",
        display_name="Чужая организация",
        is_default=True,
        requisites={},
    )
    db.add(other_issuer)
    await db.commit()

    with pytest.raises(DocumentContextError, match="юридическое лицо"):
        await DocumentContextBuilder.build(
            db,
            tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
            selection=DocumentContextSelection(
                order_id=order.id,
                legal_entity_id=other_issuer.id,
                document_type="contract",
                issue_date=date(2026, 8, 26),
            ),
        )
