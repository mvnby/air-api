"""Native catalog drafts use actual tenant prices, one transaction and receipts."""

import asyncio
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from core.command_actor import CommandActor
from models import CommandAuditEvent, Customer, OrderDocument, OrderProductLink, OrderProposal, Product, PublicWriteIdempotency
from core.config import settings
from modules.documents.application.errors import ManagedDocumentError
from schemas_connector_catalog import CatalogDocumentInput
from services.connector_catalog_document_service import ConnectorCatalogDocumentService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict
from tests.integration.test_connector_mcp_maintenance import call, client_for, grant, success
from tests.integration.test_managed_document_lifecycle import _seed


@pytest.fixture
async def catalog_document_db(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session


async def setup(db, tmp_path, document_type="offer", scopes="kitlane:read kitlane:catalog:write"):
    scope, order, issuer, storage, _ = await _seed(db, tmp_path, document_type=document_type)
    product = (await db.execute(select(Product))).scalars().one()
    product.product_kind = "complete_split_system"
    product.specs = {"area_m2": 35, "capacity_cooling_kw": 3.5, "indoor_type": "настенный"}
    db.add(product)
    await db.commit()
    token, user, _, _ = await grant(db, scopes=scopes)
    actor = CommandActor(user.id, user.username, scope, "chatgpt")
    inputs = CatalogDocumentInput(order_id=order.id, customer_id=order.customer_id,
        legal_entity_id=issuer.id, document_type=document_type, issue_date=date(2026, 10, 10),
        idempotency_key="catalog-document-test-key-0001", lines=[{
            "product_id": product.id, "quantity": 2, "expected_unit_price_byn": 1500,
        }])
    return actor, inputs, storage, token, product


@pytest.mark.asyncio
@pytest.mark.parametrize("document_type", ["offer", "invoice"])
async def test_catalog_document_native_snapshot_quantities_original_proposal_and_retry(catalog_document_db, tmp_path, document_type):
    db = catalog_document_db
    actor, inputs, storage, _, product = await setup(db, tmp_path, document_type)
    original_lines = list((await db.execute(select(OrderProductLink))).scalars())
    result = await ConnectorCatalogDocumentService.prepare(db, actor, inputs, template_storage=storage)
    assert not result.replayed and result.value.equipment_total_byn == 3000
    assert result.value.status == "draft" and not result.value.installation_included
    draft = await db.get(OrderDocument, result.value.document_id)
    proposal = await db.get(OrderProposal, result.value.proposal_id)
    assert not proposal.is_selected
    assert draft.proposal_id == proposal.id and draft.doc_type == document_type and draft.status == "draft"
    assert draft.official_date is None and draft.google_file_id is None
    lines = (await db.execute(select(OrderProductLink).where(OrderProductLink.proposal_id == proposal.id))).scalars().all()
    assert len(lines) == 1 and lines[0].quantity == 2 and lines[0].price == 1500
    assert [(line.quantity, line.price) for line in original_lines] == [(1, 1500)]
    assert (await db.get(Customer, inputs.customer_id)).type == "company"
    snapshot = draft.render_snapshot
    assert len(snapshot["table_rows"]["lines"]) == 1
    assert snapshot["table_rows"]["lines"][0]["line.quantity"] == "2"
    assert snapshot["table_rows"]["lines"][0]["line.amount"] == "3000.00"
    product.price = 1600
    db.add(product)
    await db.commit()
    replay = await ConnectorCatalogDocumentService.prepare(db, actor, inputs, template_storage=storage)
    assert replay.replayed and replay.value == result.value
    assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 1
    audits = (await db.execute(select(CommandAuditEvent))).scalars().all()
    assert len(audits) == 1 and audits[0].channel == "chatgpt" and audits[0].resource_id == draft.id


@pytest.mark.asyncio
async def test_catalog_document_changed_payload_conflicts_and_stale_price_does_not_save(catalog_document_db, tmp_path):
    db = catalog_document_db
    actor, inputs, storage, _, product = await setup(db, tmp_path)
    await ConnectorCatalogDocumentService.prepare(db, actor, inputs, template_storage=storage)
    changed = inputs.model_copy(deep=True)
    changed.lines[0].quantity = 3
    with pytest.raises(PublicWriteIdempotencyConflict):
        await ConnectorCatalogDocumentService.prepare(db, actor, changed, template_storage=storage)
    changed.idempotency_key = "catalog-document-new-price-0002"
    product.price = 1700
    db.add(product)
    await db.commit()
    with pytest.raises(ManagedDocumentError, match="price changed"):
        await ConnectorCatalogDocumentService.prepare(db, actor, changed, template_storage=storage)
    assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 1
    assert (await db.execute(select(func.count(OrderProposal.id)))).scalar_one() == 2


@pytest.mark.asyncio
async def test_catalog_document_failed_template_rolls_back_entire_proposal_and_receipt(catalog_document_db, tmp_path):
    db = catalog_document_db
    actor, inputs, storage, _, _ = await setup(db, tmp_path)
    inputs.template_id = 999999
    with pytest.raises(ManagedDocumentError):
        await ConnectorCatalogDocumentService.prepare(db, actor, inputs, template_storage=storage)
    assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 0
    assert (await db.execute(select(func.count(OrderProposal.id)))).scalar_one() == 1
    assert (await db.execute(select(func.count(PublicWriteIdempotency.id)))).scalar_one() == 0
    assert (await db.execute(select(func.count(CommandAuditEvent.id)))).scalar_one() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["order_id", "customer_id", "legal_entity_id"])
async def test_catalog_document_rejects_unknown_bindings(catalog_document_db, tmp_path, field):
    from fastapi import HTTPException
    db = catalog_document_db
    actor, inputs, storage, _, _ = await setup(db, tmp_path)
    setattr(inputs, field, 999999)
    with pytest.raises(HTTPException) as failure:
        await ConnectorCatalogDocumentService.prepare(db, actor, inputs, template_storage=storage)
    assert failure.value.status_code == 404
    assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 0


@pytest.mark.asyncio
async def test_catalog_document_real_mcp_scope_concurrency_and_revoke(catalog_document_db, tmp_path, monkeypatch):
    db = catalog_document_db
    actor, inputs, _, token, _ = await setup(db, tmp_path, document_type="invoice")
    monkeypatch.setattr(settings, "SERVICE_ATTACHMENT_LOCAL_DIR", str(tmp_path / "private-documents"))
    async with client_for(db, token) as client:
        selection = success(await call(client, "select_catalog_products", {"cooling_btu_class": 12, "quantity": 2}))
        assert selection["options"][0]["product"]["product_id"] == inputs.lines[0].product_id
        assert "3000 BYN" in selection["message_text"]
        product = success(await call(client, "get_catalog_product", {"product_id": inputs.lines[0].product_id}))
        assert product["unit_price_byn"] == inputs.lines[0].expected_unit_price_byn
        args = inputs.model_dump(mode="json")
        responses = await asyncio.gather(*[call(client, "prepare_catalog_document", args) for _ in range(3)])
        values = [success(response) for response in responses]
        assert sum(not value["replayed"] for value in values) == 1
        assert len({value["result"]["document_id"] for value in values}) == 1
        document = await db.get(OrderDocument, values[0]["result"]["document_id"])
        assert document.render_snapshot["meta"]["customer_readiness"]["checked"]
        from services.connector_auth_policy import CLIENT_ID
        from services.connector_auth_service import ConnectorAuthService
        await ConnectorAuthService.revoke_token(db, token=token.access_token, client_id=CLIENT_ID)
        rejected = await client.post("/api/connector/mcp", json={"jsonrpc": "2.0", "id": 1,
            "method": "tools/call", "params": {"name": "prepare_catalog_document", "arguments": args}})
        assert rejected.status_code == 401 and rejected.json()["error"] == "invalid_token"
    assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 1


@pytest.mark.asyncio
async def test_catalog_document_old_grant_does_not_gain_write_scope(catalog_document_db, tmp_path):
    db = catalog_document_db
    _, inputs, _, token, _ = await setup(db, tmp_path, scopes="kitlane:read kitlane:maintenance:write")
    async with client_for(db, token) as client:
        rejected = await call(client, "prepare_catalog_document", inputs.model_dump(mode="json"))
        assert rejected["isError"] and rejected["structuredContent"]["error"]["status"] == 403
        issuers = success(await call(client, "list_catalog_document_issuers", {}))
        assert issuers["items"][0]["legal_entity_id"] == inputs.legal_entity_id
    assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 0


@pytest.mark.asyncio
async def test_catalog_document_missing_customer_name_rolls_back_invoice(catalog_document_db, tmp_path):
    db = catalog_document_db
    actor, inputs, storage, _, _ = await setup(db, tmp_path, document_type="invoice")
    customer = await db.get(Customer, inputs.customer_id)
    customer.name = ""
    customer.full_legal_name = ""
    db.add(customer)
    await db.commit()
    with pytest.raises(ManagedDocumentError):
        await ConnectorCatalogDocumentService.prepare(db, actor, inputs, template_storage=storage)
    assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 0
    assert (await db.execute(select(func.count(OrderProposal.id)))).scalar_one() == 1


@pytest.mark.asyncio
async def test_catalog_document_actual_foreign_order_customer_issuer_are_rejected(catalog_document_db, tmp_path):
    from fastapi import HTTPException
    from models import DocumentLegalEntity, Order, OrderStatus, Storefront, Tenant
    db = catalog_document_db
    actor, inputs, storage, _, _ = await setup(db, tmp_path)
    db.add(Tenant(id=2, slug="foreign-catalog-doc", display_name="Foreign"))
    await db.flush()
    db.add(Storefront(id=2, tenant_id=2, slug="foreign", display_name="Foreign", status="active"))
    customer = Customer(tenant_id=2, name="Foreign customer", phone="+375290000002", type="company")
    issuer = DocumentLegalEntity(tenant_id=2, slug="foreign-issuer", display_name="Foreign issuer", legal_name="Foreign", unp="200000001")
    db.add_all([customer, issuer])
    await db.flush()
    order = Order(tenant_id=2, storefront_id=2, customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    for field, foreign_id in (("order_id", order.id), ("customer_id", customer.id), ("legal_entity_id", issuer.id)):
        with pytest.raises(HTTPException) as failure:
            await ConnectorCatalogDocumentService.prepare(db, actor, inputs.model_copy(update={field: foreign_id}), template_storage=storage)
        assert failure.value.status_code == 404
    assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 0


@pytest.mark.asyncio
async def test_catalog_document_secondary_system_storefront_uses_offer_price_and_rechecks_replay(catalog_document_db, tmp_path):
    from fastapi import HTTPException
    from models import Order, Storefront, TenantCatalogGrant, TenantOffer
    from models.tenancy import TenantScope
    from schemas_connector_catalog import CatalogProductInput
    from services.connector_catalog_selection_service import ConnectorCatalogSelectionService
    db = catalog_document_db
    actor, inputs, storage, _, product = await setup(db, tmp_path)
    storefront = Storefront(tenant_id=1, slug="secondary-document", display_name="Secondary", status="active")
    db.add(storefront)
    await db.flush()
    catalog_grant = TenantCatalogGrant(tenant_id=1, storefront_id=storefront.id, status="active",
        created_by_username="test", updated_by_username="test")
    db.add(catalog_grant)
    await db.flush()
    db.add(TenantOffer(tenant_id=1, storefront_id=storefront.id, catalog_grant_id=catalog_grant.id,
        product_id=product.id, price=800, is_published=True,
        created_by_username="test", updated_by_username="test"))
    order = await db.get(Order, inputs.order_id)
    order.storefront_id = storefront.id
    db.add(order)
    await db.commit()
    actor = CommandActor(actor.staff_user_id, actor.username,
        TenantScope(1, storefront.id, is_system=True, is_canonical_storefront=False), "chatgpt")
    selected = await ConnectorCatalogSelectionService.get_product(db, actor, CatalogProductInput(product_id=product.id))
    inputs.lines[0].expected_unit_price_byn = selected.unit_price_byn
    result = await ConnectorCatalogDocumentService.prepare(db, actor, inputs, template_storage=storage)
    document = await db.get(OrderDocument, result.value.document_id)
    assert result.value.equipment_total_byn == 1600
    row = document.render_snapshot["table_rows"]["lines"][0]
    assert row["line.unit_price"] == "800.00" and row["line.amount"] == "1600.00"
    catalog_grant.status = "disabled"
    db.add(catalog_grant)
    await db.commit()
    with pytest.raises(HTTPException) as failure:
        await ConnectorCatalogDocumentService.prepare(db, actor, inputs, template_storage=storage)
    assert failure.value.status_code == 404
    assert (await db.execute(select(func.count(OrderDocument.id)))).scalar_one() == 1


@pytest.mark.asyncio
async def test_catalog_document_commit_ack_loss_retry_returns_saved_document(catalog_document_db, tmp_path):
    db = catalog_document_db
    actor, inputs, storage, _, _ = await setup(db, tmp_path)

    class AckLost(AsyncSession):
        async def commit(self):
            await super().commit()
            raise ConnectionError("test commit acknowledgement lost")

    async with AckLost(bind=db.bind, expire_on_commit=False) as session:
        with pytest.raises(ConnectionError):
            await ConnectorCatalogDocumentService.prepare(session, actor, inputs, template_storage=storage)
    async with AsyncSession(bind=db.bind, expire_on_commit=False) as session:
        result = await ConnectorCatalogDocumentService.prepare(session, actor, inputs, template_storage=storage)
        assert result.replayed and result.value.equipment_total_byn == 3000
        assert (await session.execute(select(func.count(OrderDocument.id)))).scalar_one() == 1
        assert (await session.execute(select(func.count(CommandAuditEvent.id)))).scalar_one() == 1
