"""Chosen sales drafts retain context, native tariff provenance and retry safety."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from core.command_actor import CommandActor
from models import (
    CommandAuditEvent, Customer, InstallationEstimateRevision, InstallationPriceBook,
    Order, OrderDocument, OrderProductLink, OrderProposal, Product,
)
from schemas_connector_sales_order import (
    SalesCustomerCreateInput, SalesOrderOfferPrepareInput, SalesOrderOfferReadInput,
    SalesOrderReadInput, SalesOrderSaveInput,
)
from schemas_connector_sales_pricing import SalesInstallationInput
from services.connector_sales_order import (
    execute_sales_order_tool, get_sales_order, get_sales_order_offer, prepare_sales_order_offer,
)
from services.connector_sales_pricing import ConnectorSalesPricingService as Pricing
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict
from tests.integration.test_connector_mcp_maintenance import grant
from tests.integration.test_installation_estimate_confirmation import _entry
from tests.integration.test_managed_document_lifecycle import _seed


@pytest.fixture
async def sales_db(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session


async def setup(db, tmp_path):
    scope, original, issuer, storage, _ = await _seed(db, tmp_path, document_type="offer")
    product = (await db.execute(select(Product))).scalars().one()
    product.product_kind = "complete_split_system"
    product.specs = {"area_m2": 25, "capacity_cooling_kw": 2.5, "indoor_type": "настенный",
                     "pipe_liquid": '1/4"', "pipe_gas": '3/8"'}
    db.add(product)
    db.add(InstallationPriceBook(tenant_id=1, revision=1, fingerprint="sales-test-book", entries=[_entry()]))
    await db.commit()
    _, user, _, _ = await grant(db, scopes="kitlane:read kitlane:orders:write kitlane:catalog:write")
    actor = CommandActor(user.id, user.username, scope, "chatgpt")
    installation = SalesInstallationInput(route_length_m="6", holes_by_type={"diamond": 2}, access="standard")
    option = await Pricing.price_option(db, actor, product_id=product.id, installation=installation)
    data = SalesOrderSaveInput(customer_id=original.customer_id, product_id=product.id,
        installation=installation, expected_calculation_fingerprint=option.calculation_fingerprint,
        request_text="Исходный запрос: одна комната, кондиционер и монтаж", requirements_text="25 м², обогрев",
        address="Минск, тестовый объект", idempotency_key="sales-order-first-000001")
    return actor, data, product, issuer, storage


async def count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.mark.asyncio
async def test_save_resume_retry_and_preserve_other_proposals(sales_db, tmp_path):
    db = sales_db
    actor, data, product, _, _ = await setup(db, tmp_path)
    first = await execute_sales_order_tool(db, actor, "save_sales_order", data)
    result = first["result"]
    assert not first["replayed"]
    assert result.workflow_type == "sales_installation" and result.service_type == "turnkey"
    assert result.total_byn == Decimal("2080.75") and result.installation_total_byn == Decimal("580.75")
    assert result.requirements_text == data.requirements_text and result.request_text == data.request_text
    assert len(result.products) == len(result.services) == 1
    revision = await db.get(InstallationEstimateRevision, result.services[0].installation_estimate_revision_id)
    assert revision.snapshot["input"]["installations"][0]["route_length_m"] == "6"
    assert revision.total == Decimal("580.75") and revision.price_book_revision == 1
    order = await db.get(Order, result.order_id)
    assert order.responsible_staff_user_id == actor.staff_user_id
    alternative = OrderProposal(order_id=order.id, name="Other variant", is_selected=False)
    db.add(alternative)
    await db.flush()
    db.add(OrderProductLink(order_id=order.id, proposal_id=alternative.id, product_id=product.id, quantity=3, price=999))
    await db.commit()
    replay = await execute_sales_order_tool(db, actor, "save_sales_order", data)
    assert replay["replayed"] and replay["result"].order_id == result.order_id
    assert await count(db, Order) == 2 and await count(db, InstallationEstimateRevision) == 1
    current = await get_sales_order(db, actor, SalesOrderReadInput(order_id=result.order_id))
    data = data.model_copy(update=dict(order_id=result.order_id, proposal_id=result.proposal_id,
        expected_version=current.version, requirements_text="Новые требования", idempotency_key="sales-edit-000001"))
    edited = (await execute_sales_order_tool(db, actor, "save_sales_order", data))["result"]
    assert edited.requirements_text == "Новые требования" and edited.version != current.version
    other = (await db.execute(select(OrderProductLink).where(OrderProductLink.proposal_id == alternative.id))).scalars().one()
    assert other.quantity == 3 and other.price == 999 and not alternative.is_selected
    assert await count(db, InstallationEstimateRevision) == 2
    assert await count(db, CommandAuditEvent) == 2
    data.idempotency_key = "sales-stale-edit-0001"
    with pytest.raises(HTTPException) as exc:
        await execute_sales_order_tool(db, actor, "save_sales_order", data)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["price", "tariff"])
async def test_changed_quote_and_access_create_no_partial_order(sales_db, tmp_path, changed):
    db = sales_db
    actor, data, product, _, _ = await setup(db, tmp_path)
    if changed == "price":
        product.price = 1600
        db.add(product)
    else:
        db.add(InstallationPriceBook(tenant_id=1, revision=2, fingerprint="sales-test-revised", entries=[_entry(base_price="550.00")]))
    await db.commit()
    with pytest.raises(HTTPException) as exc:
        await execute_sales_order_tool(db, actor, "save_sales_order", data)
    assert exc.value.status_code == 409 and await count(db, Order) == 1
    assert await count(db, InstallationEstimateRevision) == 0
    data.customer_id = 999999
    with pytest.raises(HTTPException) as exc:
        await execute_sales_order_tool(db, actor, "save_sales_order", data)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("party", ["individual", "company", "individual_entrepreneur"])
async def test_explicit_customer_party_duplicate_and_idempotency(sales_db, tmp_path, party):
    db = sales_db
    actor, _, _, _, _ = await setup(db, tmp_path)
    data = SalesCustomerCreateInput(customer={"name": "Новый клиент", "type": party, "phone": "+375291234567"},
                                    idempotency_key="sales-customer-00001")
    first = await execute_sales_order_tool(db, actor, "create_sales_customer", data)
    customer = await db.get(Customer, first["result"].customer_id)
    assert str(getattr(customer.type, "value", customer.type)) == party
    assert customer.signing_mode == ("statutory_body" if party == "company" else "self")
    replay = await execute_sales_order_tool(db, actor, "create_sales_customer", data)
    assert replay["replayed"] and replay["result"].customer_id == customer.id
    data.idempotency_key = "sales-customer-duplicate"
    with pytest.raises(HTTPException) as exc:
        await execute_sales_order_tool(db, actor, "create_sales_customer", data)
    assert exc.value.status_code == 409 and exc.value.detail["customer_id"] == customer.id
    assert await count(db, Customer) == 2


@pytest.mark.asyncio
async def test_offer_uses_saved_proposal_and_old_draft_becomes_stale(sales_db, tmp_path, monkeypatch):
    db = sales_db
    actor, data, product, issuer, storage = await setup(db, tmp_path)
    saved = (await execute_sales_order_tool(db, actor, "save_sales_order", data))["result"]
    alternative = OrderProposal(order_id=saved.order_id, name="Other", is_selected=False)
    db.add(alternative)
    await db.flush()
    db.add(OrderProductLink(order_id=saved.order_id, proposal_id=alternative.id, product_id=product.id, quantity=10, price=999))
    await db.commit()
    monkeypatch.setattr("services.connector_sales_order._storage", lambda: storage)
    offer_inputs = SalesOrderOfferPrepareInput(order_id=saved.order_id,
        proposal_id=saved.proposal_id, expected_version=saved.version, legal_entity_id=issuer.id,
        issue_date=date(2026, 11, 7), idempotency_key="sales-offer-00000001")
    prepared = (await execute_sales_order_tool(db, actor, "prepare_sales_order_offer", offer_inputs))["result"]
    replay = await execute_sales_order_tool(db, actor, "prepare_sales_order_offer", offer_inputs)
    assert replay["replayed"] and replay["result"].document_id == prepared.document_id
    assert await count(db, OrderDocument) == 1
    assert prepared.status == "draft" and not prepared.stale
    assert await count(db, OrderProposal) == 3
    document = await db.get(OrderDocument, prepared.document_id)
    assert document.official_number is None and document.google_file_id is None
    rows = document.render_snapshot["table_rows"]["lines"]
    assert len(rows) == 2 and {row["line.amount"] for row in rows} == {"1500.00", "580.75"}
    current = await get_sales_order(db, actor, SalesOrderReadInput(order_id=saved.order_id))
    edit = data.model_copy(update=dict(order_id=saved.order_id, proposal_id=saved.proposal_id,
        expected_version=current.version, idempotency_key="sales-document-edit-01"))
    await execute_sales_order_tool(db, actor, "save_sales_order", edit)
    old = await get_sales_order_offer(db, actor, SalesOrderOfferReadInput(document_id=document.id), template_storage=storage)
    assert old.stale and not old.customer_ready_and_current
    assert document.render_snapshot["table_rows"]["lines"] == rows
    from modules.documents.application import ManagedDocumentService
    from modules.documents.application.errors import ManagedDocumentConflictError
    from tests.integration.test_managed_document_lifecycle import FakePdfConverter
    with pytest.raises(ManagedDocumentConflictError, match="Предложение изменилось"):
        await ManagedDocumentService.issue(db, tenant_scope=actor.tenant_scope,
            document_id=document.id, template_storage=storage, artifact_storage=object(),
            pdf_converter=FakePdfConverter())
    assert document.official_number is None


@pytest.mark.asyncio
async def test_receipt_key_payload_change_does_not_duplicate_order(sales_db, tmp_path):
    db = sales_db
    actor, data, _, _, _ = await setup(db, tmp_path)
    await execute_sales_order_tool(db, actor, "save_sales_order", data)
    data.request_text = "Другой запрос"
    with pytest.raises(PublicWriteIdempotencyConflict):
        await execute_sales_order_tool(db, actor, "save_sales_order", data)
    assert await count(db, Order) == 2 and await count(db, CommandAuditEvent) == 1


@pytest.mark.asyncio
async def test_individual_offer_and_missing_template_preserve_saved_selection(sales_db, tmp_path):
    db = sales_db
    actor, data, _, issuer, storage = await setup(db, tmp_path)
    customer = await db.get(Customer, data.customer_id)
    customer.type, customer.full_legal_name, customer.signing_mode = "individual", None, "self"
    customer.inn = customer.legal_address = customer.iban = None
    db.add(customer)
    await db.commit()
    saved = (await execute_sales_order_tool(db, actor, "save_sales_order", data))["result"]
    inputs = SalesOrderOfferPrepareInput(order_id=saved.order_id, proposal_id=saved.proposal_id,
        expected_version=saved.version, legal_entity_id=issuer.id, issue_date=date(2026, 11, 7),
        idempotency_key="sales-individual-offer-01")
    offer = await prepare_sales_order_offer(db, actor, inputs, template_storage=storage)
    assert offer.status == "draft" and not offer.stale
    assert (await db.get(Customer, data.customer_id)).type == "individual"
    # A failed subsequent document operation cannot erase the saved order.
    inputs.template_id = 999999
    from modules.documents.application.errors import ManagedDocumentError
    with pytest.raises(ManagedDocumentError):
        await prepare_sales_order_offer(db, actor, inputs, template_storage=storage)
    current = await get_sales_order(db, actor, SalesOrderReadInput(order_id=saved.order_id))
    assert current.proposal_id == saved.proposal_id and current.total_byn == saved.total_byn


@pytest.mark.asyncio
async def test_failed_audit_rolls_back_sales_composition_and_receipt(sales_db, tmp_path, monkeypatch):
    db = sales_db
    actor, data, _, _, _ = await setup(db, tmp_path)
    original_flush = db.flush

    async def flush(*args, **kwargs):
        if any(isinstance(item, CommandAuditEvent) for item in db.new):
            raise RuntimeError("audit rejected")
        return await original_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", flush)
    with pytest.raises(RuntimeError, match="audit rejected"):
        await execute_sales_order_tool(db, actor, "save_sales_order", data)
    assert await count(db, Order) == 1 and await count(db, InstallationEstimateRevision) == 0
    assert await count(db, CommandAuditEvent) == 0


@pytest.mark.asyncio
async def test_selected_accessory_saved_with_native_exact_price(sales_db, tmp_path):
    db = sales_db
    actor, data, product, _, _ = await setup(db, tmp_path)
    from models.catalog_accessory import ProductAccessoryOverride
    accessory = Product(title="Модуль Wi-Fi", slug="sales-wifi", product_kind="accessory", price=125)
    db.add(accessory)
    await db.flush()
    db.add(ProductAccessoryOverride(product_id=product.id, accessory_product_id=accessory.id, is_enabled=True))
    await db.commit()
    from services.catalog_decision_projection import CatalogDecisionQueryService
    default = await CatalogDecisionQueryService.get_product_snapshots(db, tenant_scope=actor.tenant_scope,
                                                                     product_ids=[product.id, accessory.id])
    assert set(default) == {product.id}
    data.accessory_product_ids = [accessory.id]
    option = await Pricing.price_option(db, actor, product_id=product.id, installation=data.installation,
                                        accessory_product_ids=data.accessory_product_ids)
    data.expected_calculation_fingerprint = option.calculation_fingerprint
    saved = (await execute_sales_order_tool(db, actor, "save_sales_order", data))["result"]
    assert saved.equipment_total_byn == Decimal("1500")
    assert saved.accessories_total_byn == Decimal("125") and saved.total_byn == Decimal("2205.75")
    assert {line.product_id for line in saved.products} == {product.id, accessory.id}


@pytest.mark.asyncio
async def test_foreign_customer_and_revoked_membership_reject_before_replay(sales_db, tmp_path):
    db = sales_db
    actor, data, _, _, _ = await setup(db, tmp_path)
    saved = (await execute_sales_order_tool(db, actor, "save_sales_order", data))["result"]
    from models.tenancy import Tenant, TenantMembership
    tenant = Tenant(slug="foreign-sales-customer", display_name="Other")
    db.add(tenant)
    await db.flush()
    foreign = Customer(tenant_id=tenant.id, name="Чужой клиент", phone="")
    db.add(foreign)
    await db.commit()
    foreign_data = data.model_copy(update={"customer_id": foreign.id, "idempotency_key": "sales-foreign-customer"})
    with pytest.raises(HTTPException) as exc:
        await execute_sales_order_tool(db, actor, "save_sales_order", foreign_data)
    assert exc.value.status_code == 404
    membership = (await db.execute(select(TenantMembership).where(
        TenantMembership.tenant_id == actor.tenant_scope.tenant_id,
        TenantMembership.staff_user_id == actor.staff_user_id))).scalars().one()
    membership.status = "suspended"
    db.add(membership)
    await db.commit()
    with pytest.raises(HTTPException) as exc:
        await execute_sales_order_tool(db, actor, "save_sales_order", data)
    assert exc.value.status_code == 403
    assert await count(db, Order) == 2 and saved.order_id


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["address", "title", "requirements"])
async def test_offer_source_context_change_is_stale_and_cannot_issue(sales_db, tmp_path, changed):
    db = sales_db
    actor, data, _, issuer, storage = await setup(db, tmp_path)
    saved = (await execute_sales_order_tool(db, actor, "save_sales_order", data))["result"]
    prepared = await prepare_sales_order_offer(db, actor, SalesOrderOfferPrepareInput(
        order_id=saved.order_id, proposal_id=saved.proposal_id, expected_version=saved.version,
        legal_entity_id=issuer.id, issue_date=date(2026, 11, 7),
        idempotency_key="sales-context-offer-01"), template_storage=storage)
    document = await db.get(OrderDocument, prepared.document_id)
    frozen_address = document.render_snapshot["values"]["order.object_address"]
    commercial_version = prepared.proposal_version
    if changed in {"address", "title"}:
        from schemas_manager_orders import ManagerOrderUpdatePayload
        from services.order_update.command import OrderUpdateCommandService
        changes = {"customer_delivery_address": "Минск, новый адрес"} if changed == "address" else {"title": "Другой объект"}
        await OrderUpdateCommandService.update_order_for_manager(db, saved.order_id,
            ManagerOrderUpdatePayload(**changes), tenant_scope=actor.tenant_scope)
    else:
        order = await db.get(Order, saved.order_id)
        contexts = dict(order.technical_meta["sales_selections"])
        contexts[str(saved.proposal_id)] = {**contexts[str(saved.proposal_id)], "requirements_text": "Уточнённые требования объекта"}
        order.technical_meta = {**order.technical_meta, "sales_selections": contexts}
        db.add(order)
        await db.commit()
    current = await get_sales_order_offer(db, actor,
        SalesOrderOfferReadInput(document_id=prepared.document_id), template_storage=storage)
    assert current.current_proposal_version == commercial_version
    assert current.stale and not current.customer_ready_and_current
    assert document.render_snapshot["values"]["order.object_address"] == frozen_address
    from modules.documents.application import ManagedDocumentService
    from modules.documents.application.errors import ManagedDocumentConflictError
    from tests.integration.test_managed_document_lifecycle import FakePdfConverter
    with pytest.raises(ManagedDocumentConflictError, match="Контекст заказа изменился"):
        await ManagedDocumentService.issue(db, tenant_scope=actor.tenant_scope,
            document_id=document.id, template_storage=storage, artifact_storage=object(),
            pdf_converter=FakePdfConverter())
    assert document.official_number is None


@pytest.mark.asyncio
async def test_sales_offer_native_parameter_edit_remains_current_and_issuable(sales_db, tmp_path):
    db = sales_db
    actor, data, _, issuer, storage = await setup(db, tmp_path)
    saved = (await execute_sales_order_tool(db, actor, "save_sales_order", data))["result"]
    prepared = await prepare_sales_order_offer(db, actor, SalesOrderOfferPrepareInput(
        order_id=saved.order_id, proposal_id=saved.proposal_id, expected_version=saved.version,
        legal_entity_id=issuer.id, issue_date=date(2026, 11, 7),
        idempotency_key="sales-native-parameter-01"), template_storage=storage)
    from modules.documents.application import ManagedDocumentService
    from modules.documents.application.draft_mutations import ManagedDocumentDraftMutationService
    from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
    from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
    from tests.integration.test_managed_document_lifecycle import FakePdfConverter
    parameters = await ManagedDocumentDraftMutationService.get(db,
        tenant_scope=actor.tenant_scope, document_id=prepared.document_id)
    await ManagedDocumentDraftMutationService.update(db, tenant_scope=actor.tenant_scope,
        document_id=prepared.document_id, changes={"issue_city": "Брест"}, expected_revision=parameters["revision"])
    current = await get_sales_order_offer(db, actor,
        SalesOrderOfferReadInput(document_id=prepared.document_id), template_storage=storage)
    assert not current.stale and current.customer_ready_and_current
    issued = await ManagedDocumentService.issue(db, tenant_scope=actor.tenant_scope,
        document_id=prepared.document_id, template_storage=storage,
        artifact_storage=PrivateDocumentArtifactStorage(LocalPrivateAttachmentStorage(tmp_path / "native-parameter-artifacts")),
        pdf_converter=FakePdfConverter())
    assert issued.document.status == "issued" and issued.document.official_number


@pytest.mark.asyncio
async def test_concurrent_sales_saves_keep_shared_fence_without_deadlock(db_engine, tmp_path, monkeypatch):
    import asyncio
    import services.connector_sales_order as sales
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        actor, data, _, _, _ = await setup(db, tmp_path)
    barrier = asyncio.Barrier(2)
    original = sales._access
    seen = set()

    async def synchronized_access(session, actor, inputs):
        await original(session, actor, inputs)
        if id(session) not in seen:
            seen.add(id(session))
            await asyncio.wait_for(barrier.wait(), timeout=10)

    monkeypatch.setattr(sales, "_access", synchronized_access)

    async def save(index):
        async with AsyncSession(db_engine, expire_on_commit=False) as db:
            return await sales.execute_sales_order_tool(db, actor, "save_sales_order",
                data.model_copy(update={"idempotency_key": f"concurrent-sales-save-{index:04d}"}))

    results = await asyncio.wait_for(asyncio.gather(save(1), save(2)), timeout=20)
    assert len({result["result"].order_id for result in results}) == 2
    assert all(not result["replayed"] for result in results)


@pytest.mark.asyncio
async def test_sales_access_fence_holds_tariff_publication_lock(db_engine, tmp_path):
    import asyncio
    from services.connector_sales_order import _access
    from services.installation_price_book_service import InstallationPriceBookService
    from sqlalchemy import event
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        actor, data, _, _, _ = await setup(db, tmp_path)
        from models import ServiceTariff, ServiceTariffRule
        tariff = ServiceTariff(tenant_id=1, service_kind="installation", installation_code="installation.wall.fence",
            installation_price_mode="fixed", selector_label="Монтаж",
            installation_match={"indoor_type": "wall", "match_strategy": "capacity_only",
                                "capacity_min_kw": "2", "capacity_max_kw": "4"},
            base_price=500, included_route_meters=3, included_holes_by_type={})
        db.add(tariff)
        await db.flush()
        db.add(ServiceTariffRule(tariff_id=tariff.id, rule_type="per_meter_over_included",
            component_code="route.extra_m", name="Трасса", unit="м", unit_price=10))
        await db.commit()
    async with AsyncSession(db_engine, expire_on_commit=False) as saving:
        await _access(saving, actor, data)
        async with AsyncSession(db_engine, expire_on_commit=False) as publishing:
            attempted_lock = asyncio.Event()

            def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                if "FOR NO KEY UPDATE" in statement:
                    attempted_lock.set()

            event.listen(db_engine.sync_engine, "before_cursor_execute", before_cursor_execute)
            try:
                publication = asyncio.create_task(InstallationPriceBookService.publish(
                    publishing, actor.tenant_scope, actor="sales-fence-regression", commit=False))
                await asyncio.wait_for(attempted_lock.wait(), timeout=5)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(publication), timeout=0.1)
                await saving.commit()
                await asyncio.wait_for(publication, timeout=5)
            finally:
                event.remove(db_engine.sync_engine, "before_cursor_execute", before_cursor_execute)
                if not publication.done():
                    publication.cancel()
                    await asyncio.gather(publication, return_exceptions=True)


@pytest.mark.asyncio
async def test_saved_canonical_quote_retains_verified_discount(sales_db, tmp_path):
    db = sales_db
    from models import GlobalConfig
    actor, data, product, _, _ = await setup(db, tmp_path)
    assert actor.tenant_scope.is_canonical_storefront is None
    db.add(GlobalConfig(key="install_discount", value="100"))
    await db.commit()
    option = await Pricing.price_option(db, actor, product_id=product.id, installation=data.installation)
    assert option.installation.discount == Decimal("100")
    data.expected_calculation_fingerprint = option.calculation_fingerprint
    saved = (await execute_sales_order_tool(db, actor, "save_sales_order", data))["result"]
    assert saved.installation_total_byn == option.installation_total_byn == Decimal("480.75")
    revision = await db.get(InstallationEstimateRevision, saved.services[0].installation_estimate_revision_id)
    assert revision.snapshot["result"]["discount"] == "100.00"
