"""A fresh MCP conversation can discover and adopt snapshot-only equipment."""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date, datetime

import httpx
from pydantic import ValidationError
import pytest
from sqlalchemy import func
from sqlmodel import select
from starlette.applications import Starlette
from starlette.routing import Route

from core.command_actor import CommandActor
from models import Customer, CustomerEquipment, DocumentTemplateVersion, Order, OrderDocument, OrderStatus, StaffUser
from models.tenancy import Storefront, Tenant
from modules.documents.application import ManagedDocumentService
from modules.documents.application.context_builder import DocumentContextSelection
from modules.documents.domain import ConsumerDocumentTerms
from schemas_connector_service_order_document import ConsumerDocumentsListInput, ConsumerDocumentsListResult
from services.connector_mcp import ConnectorMCPApplication
from services.connector_service_order_document import list_order_consumer_documents
from tests.integration.test_connector_consumer_documents import consumer_document_db, _setup
from tests.integration.test_managed_document_lifecycle import FakePdfConverter


async def _context(db, tmp_path):
    scope, order_id, proposal_id, issuer_id, storage, artifacts, _line, token = await _setup(db, tmp_path)
    user = await db.scalar(select(StaffUser).where(StaffUser.username == "test-consumer-mcp"))
    actor = CommandActor(user.id, user.username, scope, "chatgpt")
    return actor, order_id, proposal_id, issuer_id, storage, artifacts, token


@pytest.mark.asyncio
async def test_fresh_oauth_conversation_discovers_snapshot_only_unit_and_persists_it(consumer_document_db, tmp_path, monkeypatch):
    db = consumer_document_db
    actor, order_id, proposal_id, issuer_id, storage, artifacts, token = await _context(db, tmp_path)
    source = await ManagedDocumentService.create_draft(db, tenant_scope=actor.tenant_scope,
        selection=DocumentContextSelection(order_id=order_id, proposal_id=proposal_id,
            legal_entity_id=issuer_id, document_type="b2c_customer_equipment_installation_act",
            issue_date=date(2026, 11, 10), scope_product_line_ids=(),
            consumer_terms=ConsumerDocumentTerms(equipment_brand="TEST", equipment_model="TEST-09",
                equipment_serial="TEST-SN-001", work_warranty_months=19)), template_storage=storage)
    snapshot = deepcopy(source.render_snapshot)
    snapshot["meta"].get("draft_parameters", {}).pop("consumer_terms", None)
    source.render_snapshot = snapshot
    db.add(source)
    await db.commit()
    source_id = source.id
    issued = await ManagedDocumentService.issue(db, tenant_scope=actor.tenant_scope, document_id=source_id,
        template_storage=storage, artifact_storage=artifacts, pdf_converter=FakePdfConverter())
    frozen = deepcopy(issued.document.render_snapshot)
    checksums = {item.id: item.checksum_sha256 for item in issued.artifacts}
    assert "consumer_terms" not in frozen["meta"].get("draft_parameters", {})
    assert await db.scalar(select(func.count()).select_from(CustomerEquipment)) == 0
    db.expunge_all()  # No form, cached document or remembered ID participates in discovery.
    monkeypatch.setattr("services.connector_service_order_document._storage", lambda: storage)

    @asynccontextmanager
    async def sessions():
        yield db

    adapter = ConnectorMCPApplication(session_factory=sessions)
    app = Starlette(routes=[Route("/api/connector/mcp", adapter, methods=["GET", "POST", "DELETE"])])
    async with adapter.lifespan():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://api.mvn.by", headers={
            "Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream",
        }) as client:
            async def rpc(method, params=None, **kwargs):
                body = {"jsonrpc": "2.0", "id": 1, "method": method}
                if params is not None:
                    body["params"] = params
                return await client.post("/api/connector/mcp", json=body, **kwargs)

            async def call(name, arguments):
                response = await rpc("tools/call", {"name": name, "arguments": arguments})
                assert response.status_code == 200
                result = response.json()["result"]
                assert not result["isError"], result
                return result["structuredContent"]

            unauthenticated = await rpc("tools/call", {"name": "list_order_consumer_documents", "arguments": {"order_id": order_id}},
                headers={"Authorization": ""})
            assert unauthenticated.status_code == 401
            discovery = await rpc("tools/list")
            definition = next(tool for tool in discovery.json()["result"]["tools"] if tool["name"] == "list_order_consumer_documents")
            assert definition["annotations"]["readOnlyHint"] is True
            assert definition["_meta"]["securitySchemes"][0]["scopes"] == ["kitlane:read"]
            registry = await call("get_order_equipment", {"order_id": order_id})
            assert registry["items"] == []
            documents = await call("list_order_consumer_documents", {"order_id": order_id})
            assert documents["total"] == 1 and documents["has_more"] is False
            found = documents["items"][0]
            assert found["document_id"] == source_id and found["status"] == "issued"
            assert found["order_id"] == order_id and found["proposal_id"] == proposal_id
            assert found["legal_entity_id"] == issuer_id and found["issue_date"] == "2026-11-10"
            assert f"documentId={source_id}" in found["manager_url"]
            document = await call("get_service_order_contract", {"document_id": found["document_id"]})
            assert document["consumer_terms"]["equipment_model"] == "TEST-09"
            assert document["consumer_terms"]["equipment_serial"] == "TEST-SN-001"
            assert len(document["document_revision"]) == 64 and document["equipment_id"] is None
            adopted = await call("save_order_equipment", {"order_id": order_id,
                "expected_version": registry["version"], "source_document_id": found["document_id"],
                "idempotency_key": "consumer-discovery-adoption001"})
            equipment = adopted["result"]["equipment"]
            assert equipment["brand"] == "TEST" and equipment["model"] == "TEST-09" and equipment["serial"] == "TEST-SN-001"
            reopened = await call("get_order_equipment", {"order_id": order_id})
            assert reopened["total"] == 1 and reopened["items"][0]["equipment_id"] == adopted["result"]["equipment_id"]
    unchanged = await ManagedDocumentService.get_document(db, tenant_scope=actor.tenant_scope, document_id=source_id)
    assert unchanged.render_snapshot == frozen
    current_files = await ManagedDocumentService.list_artifacts(db, tenant_scope=actor.tenant_scope, document_id=source_id)
    assert {item.id: item.checksum_sha256 for item in current_files} == checksums


@pytest.mark.asyncio
async def test_discovery_is_bounded_and_excludes_other_document_types(consumer_document_db, tmp_path):
    db = consumer_document_db
    actor, order_id, proposal_id, issuer_id, _storage, _artifacts, _token = await _context(db, tmp_path)
    template_version_id = await db.scalar(select(DocumentTemplateVersion.id).order_by(DocumentTemplateVersion.id.desc()))
    consumer_ids = set()
    for index in range(3):
        document = OrderDocument(tenant_id=1, legal_entity_id=issuer_id, order_id=order_id, proposal_id=proposal_id,
            internal_reference=f"discovery-consumer-{index}", number=f"TEST-{index}", template_version_id=template_version_id,
            doc_type="b2c_customer_equipment_installation_act", status="issued", date=datetime(2026, 11, 10),
            render_snapshot={"values": {"equipment.model": "TEST-09"}})
        db.add(document)
        await db.flush()
        consumer_ids.add(document.id)
    unrelated = OrderDocument(tenant_id=1, legal_entity_id=issuer_id, order_id=order_id,
        internal_reference="discovery-other-contract", number="TEST-CONTRACT", doc_type="contract",
        status="issued", date=datetime(2026, 11, 10), template_version_id=template_version_id,
        render_snapshot={"values": {"private": "not consumer data"}})
    db.add(unrelated)
    await db.commit()
    first = ConsumerDocumentsListResult.model_validate(await list_order_consumer_documents(db, actor,
        ConsumerDocumentsListInput(order_id=order_id, limit=2)))
    last = ConsumerDocumentsListResult.model_validate(await list_order_consumer_documents(db, actor,
        ConsumerDocumentsListInput(order_id=order_id, limit=2, offset=2)))
    empty = ConsumerDocumentsListResult.model_validate(await list_order_consumer_documents(db, actor,
        ConsumerDocumentsListInput(order_id=order_id, limit=100, offset=3)))
    assert first.total == last.total == empty.total == 3
    assert first.has_more and not last.has_more and not empty.has_more
    assert len(first.items) == 2 and len(last.items) == 1 and empty.items == []
    assert {item.document_id for item in [*first.items, *last.items]} == consumer_ids
    with pytest.raises(ValidationError):
        ConsumerDocumentsListInput(order_id=order_id, limit=101)


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", ["tenant", "storefront", "missing_order"])
async def test_discovery_refuses_inaccessible_orders(consumer_document_db, tmp_path, foreign):
    from fastapi import HTTPException

    db = consumer_document_db
    actor, _order_id, _proposal_id, issuer_id, _storage, _artifacts, _token = await _context(db, tmp_path)
    db.add(Tenant(id=2, slug="discovery-foreign", display_name="Foreign company"))
    await db.flush()
    db.add_all([Storefront(id=2, tenant_id=2, slug="main", display_name="Foreign"),
        Storefront(id=3, tenant_id=1, slug="other", display_name="Other workspace")])
    customer = Customer(tenant_id=2 if foreign == "tenant" else 1, name="Foreign discovery customer", phone="")
    db.add(customer)
    await db.flush()
    order = Order(tenant_id=2 if foreign == "tenant" else 1, storefront_id=2 if foreign == "tenant" else 3,
                  customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    requested_id = order.id if foreign != "missing_order" else order.id + 100000
    with pytest.raises((HTTPException, LookupError)) as rejected:
        await list_order_consumer_documents(db, actor, ConsumerDocumentsListInput(order_id=requested_id))
    if isinstance(rejected.value, HTTPException):
        assert rejected.value.status_code == 404
