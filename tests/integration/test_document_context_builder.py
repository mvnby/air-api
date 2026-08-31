from datetime import date
from decimal import Decimal

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
from modules.documents.domain import (
    ActTerms,
    BusinessDocumentTerms,
    ConsumerDocumentTerms,
    PaymentScheduleItem,
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
        city="Витебск",
        bank_name="Банк покупателя",
        iban="BY00TEST00000000000000000000",
        bic="TESTBY2X",
        signer_name="Иванов И.И.",
        signing_mode="statutory_body",
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
            "city": "Витебск",
            "legal_address": "г. Витебск, ул. Продавца, 1",
            "iban": "BY00SELLER0000000000000000",
            "signing_mode": "statutory_body",
            "signer_position": "Директор",
            "signer_name": "Петров П.П.",
            "acting_basis": "Устава",
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

    assert snapshot["schema_version"] == 4
    assert snapshot["meta"]["proposal_id"] == selected.id
    assert snapshot["meta"]["business_role"] == "payment_request"
    assert snapshot["conditions"]["document.invoice_is_payment_request"] is True
    assert snapshot["conditions"]["document.invoice_is_offer"] is False
    assert snapshot["values"]["seller.unp"] == "390000000"
    assert snapshot["conditions"]["seller.is_vat_payer"] is False
    assert snapshot["conditions"]["seller.is_not_vat_payer"] is True
    assert snapshot["conditions"]["order.has_object_address"] is True
    assert snapshot["values"]["seller.entity_type"] == "organization"
    assert snapshot["values"]["seller.entity_type_label"] == "Организация"
    assert snapshot["values"]["seller.city"] == "Витебск"
    assert snapshot["values"]["document.issue_city"] == "Витебск"
    assert snapshot["values"]["seller.signing_mode"] == "statutory_body"
    assert snapshot["values"]["customer.unp"] == "123456789"
    assert snapshot["values"]["customer.entity_type"] == "organization"
    assert snapshot["values"]["customer.signing_mode"] == "statutory_body"
    assert snapshot["conditions"]["seller.organization_statutory_body"] is True
    assert snapshot["conditions"]["customer.is_individual_entrepreneur"] is False
    assert snapshot["values"]["totals.amount"] == "1400.00"
    assert [row["line.title"] for row in snapshot["table_rows"]["lines"]] == [
        "Кондиционер выбранный",
        "Монтаж кондиционера",
    ]
    assert snapshot["table_rows"]["lines"][1]["line.quantity"] == "2"

    await db.refresh(order)
    assert order.total_amount == 1_400


@pytest.mark.asyncio
async def test_context_snapshot_supports_ip_parties_and_explicit_issue_city(db):
    order, issuer, _selected, _alternative = await _seed_order(db)
    issuer.entity_type = "individual_entrepreneur"
    issuer.requisites = {
        **issuer.requisites,
        "city": "Полоцк",
        "signing_mode": "self",
    }
    customer = await db.get(Customer, order.customer_id)
    assert customer is not None
    customer.type = CustomerType.individual_entrepreneur
    customer.city = "Новополоцк"
    customer.signing_mode = "power_of_attorney"
    customer.acting_basis = "доверенности № 4 от 01.08.2026"
    db.add_all([issuer, customer])
    await db.commit()

    snapshot = await DocumentContextBuilder.build(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        selection=DocumentContextSelection(
            order_id=order.id,
            legal_entity_id=issuer.id,
            document_type="contract",
            issue_date=date(2026, 8, 27),
            issue_city="Минск",
            business_terms=BusinessDocumentTerms(
                contract_scenario="services",
                payment_schedule=(
                    PaymentScheduleItem(Decimal("100"), "before_work"),
                ),
            ),
        ),
    )

    assert snapshot["meta"]["issue_city"] == "Минск"
    assert snapshot["values"]["document.issue_city"] == "Минск"
    assert snapshot["values"]["seller.city"] == "Полоцк"
    assert snapshot["values"]["customer.city"] == "Новополоцк"
    assert snapshot["values"]["seller.entity_type"] == "individual_entrepreneur"
    assert snapshot["values"]["customer.entity_type"] == "individual_entrepreneur"
    assert snapshot["values"]["seller.signer_position"] == ""
    assert snapshot["values"]["seller.acting_basis"] == ""
    assert snapshot["conditions"]["seller.individual_entrepreneur_self"] is True
    assert (
        snapshot["conditions"]["customer.individual_entrepreneur_power_of_attorney"]
        is True
    )


@pytest.mark.asyncio
async def test_context_snapshot_repairs_legacy_odo_customer_party_for_b2b_preamble(db):
    order, issuer, _selected, _alternative = await _seed_order(db)
    customer = await db.get(Customer, order.customer_id)
    assert customer is not None
    customer.type = CustomerType.individual
    customer.signing_mode = "self"
    customer.name = "ОДО «Термотехника»"
    customer.full_legal_name = "ОДО «Термотехника»"
    customer.inn = "300566486"
    customer.legal_address = "г. Витебск, ул. Тестовая, 1"
    customer.bank_name = "ОАО «Белагропромбанк»"
    customer.iban = "BY93BAPB3013W29470010000"
    customer.bic = "BAPBBY2X"
    customer.signer_position = "директор"
    customer.signer_name = "Иванов И.И."
    customer.acting_basis = "Устава"
    db.add(customer)
    await db.commit()

    snapshot = await DocumentContextBuilder.build(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        selection=DocumentContextSelection(
            order_id=order.id,
            legal_entity_id=issuer.id,
            document_type="contract",
            issue_date=date(2026, 8, 31),
            business_terms=BusinessDocumentTerms(
                contract_scenario="installation",
                payment_schedule=(
                    PaymentScheduleItem(Decimal("100"), "before_work"),
                ),
            ),
        ),
    )

    assert snapshot["values"]["customer.entity_type"] == "organization"
    assert snapshot["values"]["customer.signing_mode"] == "statutory_body"
    assert snapshot["conditions"]["customer.organization_statutory_body"] is True
    assert snapshot["conditions"]["customer.individual_self"] is False


@pytest.mark.asyncio
async def test_contract_snapshot_keeps_b2b_terms_and_selected_proposal_scope(db):
    order, issuer, selected, _alternative = await _seed_order(db)
    issuer.is_vat_payer = True
    db.add(issuer)
    await db.commit()

    snapshot = await DocumentContextBuilder.build(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        selection=DocumentContextSelection(
            order_id=order.id,
            legal_entity_id=issuer.id,
            document_type="contract",
            issue_date=date(2026, 8, 31),
            business_terms=BusinessDocumentTerms(
                contract_scenario="supply_installation",
                goods_warranty_months=24,
                payment_schedule=(
                    PaymentScheduleItem(Decimal("70"), "before_supply"),
                    PaymentScheduleItem(Decimal("30"), "after_work"),
                ),
            ),
        ),
    )

    assert snapshot["meta"]["proposal_id"] == selected.id
    assert snapshot["values"]["contract.scenario"] == "supply_installation"
    assert snapshot["values"]["warranty.goods.months"] == "24"
    assert snapshot["conditions"]["contract.is_supply_installation"] is True
    assert snapshot["conditions"]["seller.is_vat_payer"] is True
    assert snapshot["conditions"]["seller.is_not_vat_payer"] is False
    assert snapshot["conditions"]["payment.is_equipment_prepayment_balance"] is True
    assert snapshot["table_rows"]["payment_schedule"][0]["payment.amount"] == "980.00"
    assert [row["line.title"] for row in snapshot["table_rows"]["lines"]] == [
        "Кондиционер выбранный",
        "Монтаж кондиционера",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "document_type",
    (
        "b2c_supply_installation_act",
        "b2c_customer_equipment_installation_act",
        "b2c_maintenance_repair_act",
        "b2c_route_laying_act",
    ),
)
async def test_b2c_context_is_self_contained_and_snapshots_consumer_terms(
    db, document_type
):
    order, issuer, _selected, _alternative = await _seed_order(db)
    issuer.requisites = {
        **issuer.requisites,
        "offer_url": "https://mvn.by/offer",
        "offer_version": "2026-06-04",
        "offer_published_on": "04.06.2026",
        "default_goods_warranty_months": 24,
        "default_work_warranty_months": 12,
    }
    db.add(issuer)
    await db.commit()

    snapshot = await DocumentContextBuilder.build(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        selection=DocumentContextSelection(
            order_id=order.id,
            legal_entity_id=issuer.id,
            document_type=document_type,
            issue_date=date(2026, 8, 31),
            consumer_terms=ConsumerDocumentTerms(
                equipment_brand="Midea",
                equipment_model="Breeze X",
                equipment_serial="AB-42",
                goods_warranty_months=48,
                goods_warranty_terms="При соблюдении инструкции",
                route_length_meters="12",
                route_photo_fixation_performed=True,
                route_pressure_test_performed=False,
                route_ends_capped=True,
            ),
        ),
    )

    assert snapshot["schema_version"] == 4
    assert snapshot["meta"]["base_document_id"] is None
    assert snapshot["meta"]["base_customer_contract_id"] is None
    assert snapshot["values"]["offer.url"] == "https://mvn.by/offer"
    assert snapshot["values"]["equipment.display_name"] == "Midea Breeze X"
    assert snapshot["values"]["warranty.goods.months"] == (
        "48" if document_type == "b2c_supply_installation_act" else ""
    )
    assert snapshot["values"]["warranty.work.months"] == "12"
    assert snapshot["conditions"]["warranty.goods.present"] is (
        document_type == "b2c_supply_installation_act"
    )
    assert snapshot["conditions"]["route.photo_fixation_performed"] is True
    assert snapshot["conditions"]["route.pressure_test_performed"] is False
    assert snapshot["values"]["route.photo_fixation_status"] == "выполнена"
    assert snapshot["values"]["route.pressure_test_status"] == "не выполнена"
    assert snapshot["values"]["route.ends_capped_status"] == "заглушены"


@pytest.mark.asyncio
async def test_b2c_goods_warranty_defaults_to_legal_entity_then_36_months(db):
    order, issuer, _selected, _alternative = await _seed_order(db)
    issuer.requisites = {
        **issuer.requisites,
        "offer_url": "https://mvn.by/offer",
        "offer_version": "2026-06-04",
        "offer_published_on": "04.06.2026",
        "default_goods_warranty_months": 18,
    }
    db.add(issuer)
    await db.commit()

    selection = dict(
        order_id=order.id,
        legal_entity_id=issuer.id,
        document_type="b2c_supply_installation_act",
        issue_date=date(2026, 8, 31),
    )
    configured = await DocumentContextBuilder.build(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        selection=DocumentContextSelection(**selection),
    )
    assert configured["values"]["warranty.goods.months"] == "18"

    issuer.requisites = {
        key: value
        for key, value in issuer.requisites.items()
        if key != "default_goods_warranty_months"
    }
    db.add(issuer)
    await db.commit()
    fallback = await DocumentContextBuilder.build(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        selection=DocumentContextSelection(**selection),
    )
    assert fallback["values"]["warranty.goods.months"] == "36"


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
            act_terms=ActTerms(claims_status="none"),
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
                act_terms=ActTerms(claims_status="none"),
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
                act_terms=ActTerms(claims_status="none"),
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
                act_terms=ActTerms(claims_status="none"),
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
