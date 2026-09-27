from datetime import datetime

import pytest
from sqlmodel import select

from api_contracts.multi_split import ManagerMultiSplitSavePayload, MultiSplitLeadPayload, MultiSplitPreviewRequest
from models import Customer, CustomerType, Lead, LeadMultiSplitConfiguration, MultiSplitCompatibilityProfile, Order, OrderStatus, Product, ProductTagLink, Tag, TagGroup
from services.multi_split_configuration_service import MultiSplitConfigurationService, MultiSplitSelectionError
from services.multi_split_lead_transfer_service import MultiSplitLeadTransferService
from services.multi_split_lead_service import MultiSplitLeadService
from services.multi_split_proposal_service import MultiSplitProposalService, MultiSplitStalePreviewError


@pytest.mark.asyncio
async def test_multi_split_options_and_source_gated_preview(db, tenant_scope):
    group = TagGroup(title="Multi split test", slug="multi-split-test-group", is_public=True)
    db.add(group)
    await db.flush()
    tag = Tag(title="Multi split test", slug="cat-multi", group_id=group.id, is_public=True)
    db.add(tag)
    await db.flush()
    outdoor = Product(title="Test outdoor", slug="test-multi-outdoor", price=2000, product_kind="outdoor_unit")
    indoor = Product(title="Test indoor", slug="test-multi-indoor", price=800, product_kind="indoor_unit")
    hidden = Product(title="Test hidden indoor", slug="test-multi-hidden", price=100, product_kind="indoor_unit", is_published=False)
    unrelated = Product(title="Test regular split", slug="test-multi-regular", price=1200, product_kind="complete_split_system")
    db.add_all([outdoor, indoor, hidden, unrelated])
    await db.flush()
    db.add_all([
        ProductTagLink(product_id=outdoor.id, tag_id=tag.id),
        ProductTagLink(product_id=indoor.id, tag_id=tag.id),
        ProductTagLink(product_id=hidden.id, tag_id=tag.id),
    ])
    await db.flush()

    options = await MultiSplitConfigurationService.list_options(
        db, tenant_scope=tenant_scope, kind="indoor_unit", page=1, limit=1,
    )
    assert [item.id for item in options.items] == [indoor.id]
    assert options.meta.total == 1

    request = MultiSplitPreviewRequest.model_validate({
        "outdoor_product_id": outdoor.id,
        "rooms": [{"name": "Комната", "indoor_product_id": indoor.id}],
    })
    unverified = await MultiSplitConfigurationService.preview(db, tenant_scope=tenant_scope, request=request)
    assert unverified.public.status == "requires_specialist"
    assert unverified.public.composition_complete is False
    assert unverified.public.equipment_total_byn == 2800
    assert len(unverified.public.components) == 2

    db.add(MultiSplitCompatibilityProfile(
        outdoor_product_id=outdoor.id,
        verification_status="verified",
        source_url="https://manufacturer.example/models.pdf",
        source_version="2026-09",
        verified_at=datetime(2026, 9, 27),
        allowed_indoor_product_ids=[indoor.id],
        exact_combinations=[{"lines": [{"indoor_product_id": indoor.id, "quantity": 1}]}],
        max_indoor_units=2,
    ))
    await db.flush()
    confirmed = await MultiSplitConfigurationService.preview(db, tenant_scope=tenant_scope, request=request)
    assert confirmed.public.status == "confirmed"
    assert confirmed.public.composition_complete is True

    hidden_request = MultiSplitPreviewRequest.model_validate({
        "outdoor_product_id": outdoor.id,
        "rooms": [{"name": "Комната", "indoor_product_id": hidden.id}],
    })
    with pytest.raises(MultiSplitSelectionError):
        await MultiSplitConfigurationService.preview(db, tenant_scope=tenant_scope, request=hidden_request)

    customer = Customer(tenant_id=1, name="Multi split customer", phone="+375291234567", type=CustomerType.individual)
    db.add(customer)
    await db.flush()
    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.flush()
    save_payload = ManagerMultiSplitSavePayload(
        **request.model_dump(),
        expected_status="confirmed",
        expected_components=confirmed.public.components,
    )
    saved = await MultiSplitProposalService.save(db, tenant_scope=tenant_scope, order_id=order.id, payload=save_payload)
    configurations = [proposal for proposal in saved["proposals"] if proposal["multi_split_configuration"]]
    assert len(configurations) == 1
    assert len(configurations[0]["product_lines"]) == 2
    assert configurations[0]["multi_split_configuration"]["verification_status"] == "confirmed"

    indoor.price = 900
    db.add(indoor)
    await db.flush()
    with pytest.raises(MultiSplitStalePreviewError):
        await MultiSplitProposalService.save(db, tenant_scope=tenant_scope, order_id=order.id, payload=save_payload)

    lead_payload = MultiSplitLeadPayload(
        configuration=request,
        name="Заявка на мультисплит",
        phone="+375291234569",
        consent=True,
    )
    first = await MultiSplitLeadService.create(db, tenant_scope=tenant_scope, payload=lead_payload, idempotency_key="multi-lead-test-001")
    replay = await MultiSplitLeadService.create(db, tenant_scope=tenant_scope, payload=lead_payload, idempotency_key="multi-lead-test-001")
    assert replay.lead_id == first.lead_id
    lead_configurations = (await db.execute(
        select(LeadMultiSplitConfiguration).where(LeadMultiSplitConfiguration.lead_id == first.lead_id)
    )).scalars().all()
    assert len(lead_configurations) == 1
    assert lead_configurations[0].rooms[0]["name"] == "Комната"


@pytest.mark.asyncio
async def test_public_lead_transfer_keeps_snapshot_as_one_draft(db, tenant_scope):
    customer = Customer(tenant_id=1, name="Lead customer", phone="+375291234568", type=CustomerType.individual)
    product = Product(title="Lead unit", slug="multi-lead-unit", price=999, product_kind="indoor_unit")
    lead = Lead(tenant_id=1, storefront_id=1, name="Lead customer", phone="+375291234568", request_text="Мультисплит")
    db.add_all([customer, product, lead])
    await db.flush()
    db.add(LeadMultiSplitConfiguration(
        lead_id=int(lead.id),
        rooms=[{"name": "Комната", "indoor_product_id": int(product.id)}],
        component_snapshot=[{
            "product_id": int(product.id), "title": "Lead unit", "product_kind": "indoor_unit",
            "quantity": 1, "unit_price_byn": 800, "total_price_byn": 800, "availability": "out_of_stock",
        }],
        verification_status="requires_specialist",
    ))
    await db.flush()
    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.flush()

    await MultiSplitLeadTransferService.transfer(db, lead_id=int(lead.id), order=order)
    from services.order_projection_service import OrderProjectionService

    detail = await OrderProjectionService.get_order_detail_for_manager(db, int(order.id), tenant_scope=tenant_scope)
    configurations = [item for item in detail["proposals"] if item["multi_split_configuration"]]
    assert len(configurations) == 1
    assert configurations[0]["status"] == "draft"
    assert configurations[0]["product_lines"][0]["price"] == 800
    assert configurations[0]["multi_split_configuration"]["rooms"][0]["name"] == "Комната"
