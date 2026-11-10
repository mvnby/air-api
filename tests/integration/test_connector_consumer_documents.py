"""OAuth/MCP continues a saved 600 BYN consumer installation document."""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date
from io import BytesIO
from urllib.parse import parse_qs, urlsplit

from docx import Document
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from starlette.applications import Starlette
from starlette.routing import Route

from core.security import AuthenticatedUser
from models import Customer, CustomerEquipment, CustomerType, DocumentTemplate, OrderDocument, OrderProductLink, OrderProposal, OrderServiceLink, StaffUser
from models.tenancy import TenantMembership
from modules.documents.application import ManagedDocumentService, NativeTemplateVersionService
from modules.documents.application.draft_preview import ManagedDocumentDraftPreviewService
from modules.documents.application.native_template_discovery import discover_native_placeholder_contract
from services.connector_auth_policy import CLIENT_ID, pkce, resource
from services.connector_auth_service import ConnectorAuthService
from services.connector_mcp import ConnectorMCPApplication
from tests.integration.test_managed_document_lifecycle import FakePdfConverter, _seed


@pytest.fixture
async def consumer_document_db(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session


def _nameplate_template():
    document = Document()
    document.add_paragraph("TEST акт № {{ document.official_full_number }} от {{ document.issued_on }}")
    document.add_paragraph("Оборудование: {{ equipment.brand }} {{ equipment.model }}; SN {{ equipment.serial }}")
    document.add_paragraph("Всего {{ totals.amount }} BYN")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Тестовая работа", "Сумма"
    table.rows[1].cells[0].text = "{{ lines }}{{ line.title }}"
    table.rows[1].cells[1].text = "{{ line.amount }}"
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _text(content):
    doc = Document(BytesIO(content))
    return "\n".join([paragraph.text for paragraph in doc.paragraphs] + [cell.text for table in doc.tables for row in table.rows for cell in row.cells])


class _CapturePdfConverter(FakePdfConverter):
    docx = None

    def convert_docx(self, content, *, filename="document.docx"):
        self.docx = content
        return super().convert_docx(content, filename=filename)


async def _setup(db, tmp_path):
    kind = "b2c_customer_equipment_installation_act"
    scope, order, issuer, storage, artifacts = await _seed(db, tmp_path, document_type=kind)
    customer = await db.get(Customer, order.customer_id)
    customer.type = CustomerType.individual
    order.workflow_type = "service_work"
    issuer.requisites = {"offer_url": "https://example.test/test-offer", "offer_version": "TEST-1", "offer_published_on": "01.11.2026"}
    proposal = await db.scalar(select(OrderProposal).where(OrderProposal.order_id == order.id))
    for product in (await db.execute(select(OrderProductLink).where(OrderProductLink.order_id == order.id))).scalars():
        await db.delete(product)
    line = OrderServiceLink(order_id=order.id, proposal_id=proposal.id,
        title="TEST монтаж оборудования заказчика", quantity=1, price=600)
    user = StaffUser(username="test-consumer-mcp", display_name="TEST manager", primary_role="admin", roles=["admin"])
    db.add_all([customer, order, issuer, line, user])
    await db.flush()
    membership = TenantMembership(tenant_id=scope.tenant_id, staff_user_id=user.id, role="admin")
    db.add(membership)
    await db.commit()
    template = await db.scalar(select(DocumentTemplate).where(DocumentTemplate.doc_type == kind))
    content = _nameplate_template()
    version = await NativeTemplateVersionService.upload_native_docx_version(db, tenant_scope=scope,
        legal_entity_id=issuer.id, template_id=template.id, filename="TEST-nameplate.docx", content=content,
        placeholder_contract=discover_native_placeholder_contract(content), storage=storage)
    await NativeTemplateVersionService.activate_version(db, tenant_scope=scope, legal_entity_id=issuer.id,
        template_id=template.id, version_id=version.id)
    auth = AuthenticatedUser(username=user.username, auth_source="staff", staff_user_id=user.id,
        role="admin", tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
        tenant_membership_id=membership.id, is_system_tenant=True, auth_version=1)
    verifier, redirect = "c" * 64, "https://chatgpt.com/connector_platform_oauth_redirect"
    pending, nonce = await ConnectorAuthService.start_consent(db, auth, "consumer-test-session", client_id=CLIENT_ID,
        redirect_uri=redirect, requested_resource=resource(), scope="kitlane:read kitlane:orders:write kitlane:contracts:drafts:write",
        state="consumer-state", code_challenge=pkce(verifier), code_challenge_method="S256", response_type="code")
    callback = await ConnectorAuthService.finish_consent(db, auth, "consumer-test-session", consent_id=pending.id, nonce=nonce, allow=True)
    token = await ConnectorAuthService.exchange_code(db, code=parse_qs(urlsplit(callback).query)["code"][0],
        client_id=CLIENT_ID, redirect_uri=redirect, requested_resource=resource(), code_verifier=verifier)
    return scope, order.id, proposal.id, issuer.id, storage, artifacts, line, token.access_token


@pytest.mark.asyncio
async def test_mcp_consumer_act_and_date_only_replacement_keep_saved_equipment_and_total(consumer_document_db, tmp_path, monkeypatch):
    db = consumer_document_db
    scope, order_id, proposal_id, issuer_id, storage, artifacts, line, token = await _setup(db, tmp_path)
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
            async def call(name, arguments):
                response = await client.post("/api/connector/mcp", json={"jsonrpc": "2.0", "id": 1,
                    "method": "tools/call", "params": {"name": name, "arguments": arguments}})
                assert response.status_code == 200
                result = response.json()["result"]
                assert not result["isError"], result
                return result["structuredContent"]

            state = await call("get_order_equipment", {"order_id": order_id})
            equipment = (await call("save_order_equipment", {"order_id": order_id,
                "expected_version": state["version"], "idempotency_key": "consumer-equipment-test001",
                "brand": "TEST", "model": "TEST-09", "serial": "TEST-SN-001"}))["result"]
            proposal = await call("get_service_order_proposal", {"order_id": order_id, "proposal_id": proposal_id})
            original_args = {"order_id": order_id, "proposal_id": proposal_id,
                "expected_version": proposal["version"], "legal_entity_id": issuer_id,
                "document_type": "b2c_customer_equipment_installation_act", "issue_date": "2026-11-10",
                "consumer_terms": {"equipment_id": equipment["equipment_id"], "work_warranty_months": 19},
                "idempotency_key": "consumer-document-test001"}
            original_result = (await call("prepare_service_order_contract", original_args))["result"]
            original_id = original_result["document_id"]
            assert original_result["equipment_id"] == equipment["equipment_id"]
            assert original_result["consumer_terms"]["equipment_model"] == "TEST-09"
            assert original_result["consumer_terms"]["equipment_serial"] == "TEST-SN-001"
            assert original_result["total_byn"] == "600.00"
            assert f"documentId={original_id}" in original_result["manager_url"]
            assert len(original_result["document_revision"]) == 64
            replay = await call("prepare_service_order_contract", original_args)
            assert replay["replayed"] and replay["result"]["document_id"] == original_id
            issued = await ManagedDocumentService.issue(db, tenant_scope=scope, document_id=original_id,
                template_storage=storage, artifact_storage=artifacts, pdf_converter=FakePdfConverter())
            frozen = deepcopy(issued.document.render_snapshot)
            issued_files = [(file.id, file.checksum_sha256) for file in issued.artifacts]
            rendered = next(file for file in issued.artifacts if file.kind == "rendered_docx")
            rendered_text = _text(await artifacts.read(ManagedDocumentService.stored_artifact(rendered)))
            assert "TEST-09" in rendered_text and "TEST-SN-001" in rendered_text and "600.00" in rendered_text
            source = await call("get_service_order_contract", {"document_id": original_id})
            assert source["status"] == "issued" and source["equipment_id"] == equipment["equipment_id"]
            card = await db.get(CustomerEquipment, equipment["equipment_id"])
            card.model, card.serial = "CHANGED-MODEL", "CHANGED-SERIAL"
            line.price = 900
            db.add_all([card, line])
            await db.commit()
            # This fresh server read represents reopening the deal in a new conversation.
            proposal = await call("get_service_order_proposal", {"order_id": order_id, "proposal_id": proposal_id})
            replacement = (await call("prepare_service_order_contract", {
                "order_id": order_id, "proposal_id": proposal_id, "expected_version": proposal["version"],
                "legal_entity_id": issuer_id, "document_type": "b2c_customer_equipment_installation_act",
                "issue_date": "2026-11-11", "replaces_document_id": original_id,
                "expected_document_revision": source["document_revision"], "idempotency_key": "consumer-replacement-test001"}))["result"]
            assert replacement["document_id"] != original_id and replacement["total_byn"] == "600.00"
            assert replacement["equipment_id"] == equipment["equipment_id"]
            assert replacement["consumer_terms"]["equipment_model"] == "TEST-09"
            assert replacement["consumer_terms"]["equipment_serial"] == "TEST-SN-001"
            assert replacement["consumer_terms"]["work_warranty_months"] == 19
            persisted = await db.get(OrderDocument, replacement["document_id"])
            assert persisted.date.date() == date(2026, 11, 11)
            assert persisted.render_snapshot["table_rows"] == frozen["table_rows"]
            converter = _CapturePdfConverter()
            await ManagedDocumentDraftPreviewService.render_pdf(db, tenant_scope=scope,
                document_id=persisted.id, template_storage=storage, artifact_storage=artifacts, pdf_converter=converter)
            replacement_text = _text(converter.docx)
            assert "TEST-09" in replacement_text and "TEST-SN-001" in replacement_text and "600.00" in replacement_text
            assert "CHANGED-MODEL" not in replacement_text and "900.00" not in replacement_text
            original = await db.get(OrderDocument, original_id)
            assert original.render_snapshot == frozen
            current_files = await ManagedDocumentService.list_artifacts(db, tenant_scope=scope, document_id=original_id)
            assert [(file.id, file.checksum_sha256) for file in current_files] == issued_files
            assert replacement["inherits_source_snapshot"] and not replacement["stale"]
            # A deliberate correction of an issued snapshot can still be issued even if
            # today's proposal has changed; the first draft's stale-source guard remains.
            revised = await ManagedDocumentService.issue(db, tenant_scope=scope,
                document_id=replacement["document_id"], template_storage=storage,
                artifact_storage=artifacts, pdf_converter=_CapturePdfConverter())
            assert revised.document.status == "issued"
            assert revised.document.render_snapshot["values"]["equipment.serial"] == "TEST-SN-001"
            assert revised.document.render_snapshot["values"]["totals.amount"] == "600.00"
