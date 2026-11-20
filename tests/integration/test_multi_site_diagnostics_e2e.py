"""Acceptance of one service order across Manager, MCP, and private files."""

from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
from importlib import import_module
from io import BytesIO
from uuid import uuid4

from docx import Document
from httpx import ASGITransport, AsyncClient
import pytest
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from core.database import get_session
from models import (
    Customer, CustomerBranch, CustomerEquipment, CustomerType, DocumentLegalEntity, EquipmentServiceHistory,
    Order, OrderDocument, OrderProposal, OrderServiceLink, OrderStatus, StaffUser, TenantMembership,
)
from models.tenancy import TenantScope
from modules.documents.application.lifecycle_service import ManagedDocumentService
from modules.documents.application.native_template_discovery import discover_native_placeholder_contract
from modules.documents.application.template_versions import NativeTemplateVersionService
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_connector_mcp_maintenance import call, client_for, grant, success
from tests.integration.test_managed_document_lifecycle import FakePdfConverter
from tests.integration.test_manager_access_permissions import _headers


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
ISSUE_DATE = "2026-11-20"
AGREED_PRICE = Decimal("900.00")
SERVICE_TITLE = "Диагностика трёх объектов с логистикой"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
async def acceptance_workspace(db_engine, tmp_path, monkeypatch):
    from main import app

    private = LocalPrivateAttachmentStorage(tmp_path / "documents")
    monkeypatch.setattr(import_module("modules.documents.api.router"), "get_private_attachment_storage", lambda *args: private)
    monkeypatch.setattr(
        "modules.documents.application.external_order_documents.get_private_attachment_storage", lambda *args: private,
    )
    monkeypatch.setattr("services.connector_order_documents.get_private_attachment_storage", lambda *args: private)

    async def manager_session():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = manager_session
    try:
        async with AsyncSession(db_engine, expire_on_commit=False) as db:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as manager:
                yield db, manager, private
    finally:
        app.dependency_overrides.pop(get_session, None)


async def seed_order(db):
    customer = Customer(
        tenant_id=1, type=CustomerType.company, name="ООО Тестовый заказчик", phone="",
        inn="100000001", full_legal_name="ООО Тестовый заказчик", legal_address="Условный адрес заказчика",
        signing_mode="statutory_body", signer_name="Тестовый представитель",
    )
    issuer = DocumentLegalEntity(
        tenant_id=1, slug="acceptance-only-issuer", display_name="Тестовый исполнитель",
        legal_name="ООО Тестовый исполнитель", unp="100000002", is_default=True,
        requisites={"city": "Витебск", "legal_address": "Условный адрес исполнителя",
                    "signing_mode": "statutory_body", "signer_name": "Тестовый представитель",
                    "signer_position": "Директор", "acting_basis": "Устава"},
    )
    staff = StaffUser(
        username="acceptance-only-manager", display_name="Тестовый менеджер",
        roles=["manager"], primary_role="manager",
    )
    db.add_all([customer, issuer, staff])
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=staff.id, role="manager"))
    branches = [
        CustomerBranch(customer_id=customer.id, name=f"Объект {label}", delivery_address=f"Условный адрес {label}")
        for label in ("A", "B")
    ]
    db.add_all(branches)
    await db.flush()
    order = Order(
        tenant_id=1, storefront_id=1, customer_id=customer.id, customer_branch_id=branches[0].id,
        workflow_type="service_work", status=OrderStatus.EXECUTION, total_amount=AGREED_PRICE,
    )
    known_unit = CustomerEquipment(
        customer_id=customer.id, customer_branch_id=branches[1].id, display_name="Кондиционер B1",
    )
    db.add_all([order, known_unit])
    await db.flush()
    proposal = OrderProposal(order_id=order.id, name="Согласованная диагностика", is_selected=True, status="accepted")
    db.add(proposal)
    await db.flush()
    line = OrderServiceLink(order_id=order.id, proposal_id=proposal.id, title=SERVICE_TITLE, quantity=1, price=AGREED_PRICE)
    db.add(line)
    await db.commit()
    return order, proposal, line, issuer, branches, known_unit, _headers(staff)


def pdf_bytes(title):
    output = BytesIO()
    pdf = Canvas(output)
    pdf.setTitle(title)
    pdf.drawString(72, 720, title)
    pdf.save()
    return output.getvalue()


def docx_bytes(document):
    output = BytesIO()
    document.save(output)
    return output.getvalue()


async def activate_act_template(db, issuer_id, storage):
    template = await NativeTemplateVersionService.create_template(
        db, tenant_scope=SCOPE, legal_entity_id=issuer_id, name="Акт тестовой диагностики", doc_type="act",
    )
    doc = Document()
    doc.add_paragraph("Акт № {{ document.official_full_number }}")
    doc.add_paragraph("Объекты: {{ order.object_address }}")
    doc.add_paragraph("Договор № {{ basis.number }}")
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "{{ lines }}{{ line.title }} · {{ line.quantity }} · {{ line.amount }}"
    source = docx_bytes(doc)
    version = await NativeTemplateVersionService.upload_native_docx_version(
        db, tenant_scope=SCOPE, legal_entity_id=issuer_id, template_id=template.id, filename="acceptance-act.docx",
        content=source, placeholder_contract=discover_native_placeholder_contract(source), storage=storage,
    )
    await NativeTemplateVersionService.activate_version(
        db, tenant_scope=SCOPE, legal_entity_id=issuer_id, template_id=template.id, version_id=version.id,
    )


def response_json(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_multi_site_service_diagnostics_end_to_end(acceptance_workspace):
    db, manager, private = acceptance_workspace
    order, proposal, line, issuer, (branch_a, branch_b), known_unit, headers = await seed_order(db)
    order_path = f"/api/manager/orders/{order.id}"
    docs_path = f"{order_path}/documents"
    mcp_order = {"order_id": order.id}
    token, *_ = await grant(db, scopes="kitlane:read kitlane:orders:write kitlane:contracts:drafts:write")
    originals = {}

    async def manager_post(path, payload):
        response = await manager.post(path, headers=headers, json=payload)
        return response_json(response)

    async def manager_get(path, **params):
        response = await manager.get(path, headers=headers, params=params)
        return response_json(response)

    async def add_site(**payload):
        result = await manager_post(f"{order_path}/sites", {"payload": payload, "idempotency_key": str(uuid4())})
        return result["result"]

    async def add_equipment(site, **payload):
        endpoint = f"{order_path}/sites/{site['id']}/equipment"
        result = await manager_post(endpoint, {
            "payload": {"expected_version": site["version"], **payload}, "idempotency_key": str(uuid4()),
        })
        return result["result"]["site"], result["result"]["equipment"]["equipment_id"]

    def inspection_scope(site, equipment_id):
        return {**mcp_order, "site_id": site["id"], "equipment_id": equipment_id}

    legacy = await manager_get(f"{order_path}/sites")
    assert legacy["items"] == [] and legacy["legacy_primary"]["customer_branch_id"] == branch_a.id
    a = await add_site(customer_branch_id=branch_a.id)
    b = await add_site(customer_branch_id=branch_b.id)
    c = await add_site(title="Объект C", address="Условный адрес C")
    a, unit_a = await add_equipment(a, equipment={"display_name": "Кондиционер A без шильдика"})
    b, unit_b1 = await add_equipment(b, equipment_id=known_unit.id)
    b, unit_b2 = await add_equipment(b, equipment={"display_name": "Кондиционер B2", "components": [
        {"component_type": "indoor_unit", "model": "TEST-B2-IN"},
        {"component_type": "outdoor_unit", "model": "TEST-B2-OUT"},
    ]})
    c, unit_c = await add_equipment(c, equipment={"display_name": "Кондиционер C", "components": [
        {"component_type": "drain_pump", "title": "Дренажный насос"},
    ]})
    assert (await manager_get(f"{order_path}/sites"))["legacy_primary"] is None

    contract_bytes = pdf_bytes("Synthetic service agreement TEST-1278")
    contract_request = {"number": "TEST-1278", "contract_date": "2026-11-01T00:00:00", "external_status": "signed"}
    contract = response_json(await manager.post(
        f"{docs_path}/external-contract", data=contract_request, headers={**headers, "Idempotency-Key": str(uuid4())},
        files={"file": ("Тестовый договор.pdf", contract_bytes, "application/pdf")},
    ))
    originals[(contract["id"], 1)] = contract_bytes
    assert (contract["origin"], contract["external_status"], contract["status"]) == ("external_upload", "signed", None)

    async with client_for(db, token) as mcp:
        site_list = success(await call(mcp, "list_order_sites", mcp_order))
        assert {site["id"] for site in site_list["items"]} == {a["id"], b["id"], c["id"]}
        assert all(f"orderSiteId={site['id']}" in site["manager_url"] for site in site_list["items"])
        for site, unit_ids in ((a, [unit_a]), (b, [unit_b1, unit_b2]), (c, [unit_c])):
            found = success(await call(mcp, "list_site_equipment", {**mcp_order, "site_id": site["id"]}))
            assert {item["equipment_id"] for item in found["items"]} == set(unit_ids)

        defect = {
            **inspection_scope(a, unit_a), "expected_version": 0, "idempotency_key": str(uuid4()),
            "status": "defect_found", "facts": "Обнаружен существенный недостаток хладагента.",
            "recommendations": "Отдельно согласовать поиск и устранение утечки.",
        }
        saved = success(await call(mcp, "save_order_inspection", defect))
        assert saved["result"]["version"] == 1
        assert success(await call(mcp, "save_order_inspection", defect)) == {**saved, "replayed": True}
        stale = await call(mcp, "save_order_inspection", {**defect, "idempotency_key": str(uuid4())})
        assert stale["isError"] and stale["structuredContent"]["error"]["status"] == 409

        healthy = {"status": "no_defect_found", "facts": "На момент осмотра оборудование работает штатно.",
                   "event_history": "Редкие ошибки в журнале не повторились при проверке."}
        restored = {"status": "restored", "facts": "После очистки возобновился отвод конденсата.",
                    "performed_actions": "Очищен дренажный насос в рамках оплаченной диагностики."}
        for site, unit_id, facts in ((b, unit_b1, healthy), (b, unit_b2, healthy), (c, unit_c, restored)):
            endpoint = f"{order_path}/sites/{site['id']}/equipment/{unit_id}/inspection"
            recorded = response_json(await manager.put(endpoint, headers=headers, json={
                **facts, "expected_version": 0, "idempotency_key": str(uuid4()),
            }))
            assert recorded["result"]["version"] == 1
        inspection_c = success(await call(mcp, "get_order_inspection", inspection_scope(c, unit_c)))
        assert inspection_c["inspection"]["performed_actions"] == restored["performed_actions"]

        async def prepare_technical(site, units, kind):
            payload = {
                "idempotency_key": str(uuid4()), "expected_site_version": site["version"], "document_type": kind,
                "issue_date": ISSUE_DATE, "legal_entity_id": issuer.id, "base_document_id": contract["id"],
                "inspections": [{"equipment_id": unit_id, "expected_version": 1} for unit_id in units],
            }
            if kind == "defect_act":
                reply = success(await call(mcp, "prepare_order_defect_act", {**mcp_order, "site_id": site["id"], **payload}))
            else:
                reply = await manager_post(f"{order_path}/sites/{site['id']}/technical-acts", payload)
            result = reply["result"]
            assert result["status"] == "draft" and f"documentId={result['document_id']}" in result["manager_url"]
            row = await db.get(OrderDocument, result["document_id"])
            assert row.base_document_id == contract["id"] and row.scope_meta["site_ids"] == [site["id"]]
            assert row.scope_meta["equipment_ids"] == units and "totals.amount" not in row.render_snapshot["values"]
            return row

        draft_a = await prepare_technical(a, [unit_a], "defect_act")
        draft_b = await prepare_technical(b, [unit_b1, unit_b2], "technical_inspection_act")
        draft_c = await prepare_technical(c, [unit_c], "technical_inspection_act")
        a_rows = draft_a.render_snapshot["table_rows"]["inspections"]
        assert a_rows[0]["inspection.performed_actions"] == "—"
        assert defect["recommendations"] in a_rows[0]["inspection.recommendations"]
        b_rows = draft_b.render_snapshot["table_rows"]["inspections"]
        assert len(b_rows) == 2
        assert all(healthy["event_history"] in row["inspection.event_history"] for row in b_rows)
        c_rows = draft_c.render_snapshot["table_rows"]["inspections"]
        assert restored["performed_actions"] in c_rows[0]["inspection.performed_actions"]

        templates = PrivateTemplateSourceStorage(private)
        artifacts = PrivateDocumentArtifactStorage(private)
        await activate_act_template(db, issuer.id, templates)
        completion_source = await manager_get(f"{order_path}/completion-acts/source", proposal_id=proposal.id)
        completion_payload = {
            "idempotency_key": str(uuid4()), "expected_proposal_version": completion_source["proposal_version"],
            "proposal_id": proposal.id, "site_ids": [a["id"], b["id"], c["id"]], "base_document_id": contract["id"],
            "issue_date": ISSUE_DATE, "issue_city": "Витебск", "legal_entity_id": issuer.id,
            "document_role_type": "executor_customer", "act_terms": {"claims_status": "none"},
        }
        completion_result = await manager_post(f"{order_path}/completion-acts", completion_payload)
        completion_id = completion_result["result"]["document_id"]
        repeated = await manager_post(f"{order_path}/completion-acts", completion_payload)
        assert repeated == {**completion_result, "replayed": True}

        issued = await ManagedDocumentService.issue(
            db, tenant_scope=SCOPE, document_id=completion_id, template_storage=templates,
            artifact_storage=artifacts, pdf_converter=FakePdfConverter(),
        )
        full_act = issued.document
        commercial_rows = full_act.render_snapshot["table_rows"]["lines"]
        assert len(commercial_rows) == 1
        assert commercial_rows[0]["line.title"] == SERVICE_TITLE
        assert commercial_rows[0]["line.quantity"] == "1" and commercial_rows[0]["line.amount"] == str(AGREED_PRICE)
        assert full_act.scope_meta["site_ids"] == completion_payload["site_ids"] and full_act.status == "issued"
        assert full_act.base_document_id == contract["id"] and full_act.proposal_id == proposal.id
        artifact = next(file for file in issued.artifacts if file.kind == "rendered_docx")
        content = await artifacts.read(ManagedDocumentService.stored_artifact(artifact))
        texts = [paragraph.text for paragraph in Document(BytesIO(content)).paragraphs]
        assert any(all(site["address"] in text for site in (a, b, c)) for text in texts)
        assert any(contract["number"] in text for text in texts)
        frozen = deepcopy(full_act.render_snapshot)

        word = Document()
        word.add_paragraph("Недостаток хладагента. Рекомендован отдельный поиск утечки.")
        word_evidence = docx_bytes(word)
        evidence_args = {
            "document_type": "defect_act", "number": "TEST-DEF-A", "document_date": ISSUE_DATE,
            "site_id": str(a["id"]), "equipment_ids": [str(unit_a)], "base_document_id": str(contract["id"]),
            "proposal_id": str(proposal.id),
        }
        evidence_headers = {**headers, "Idempotency-Key": str(uuid4())}

        async def upload_defect():
            return response_json(await manager.post(
                f"{docs_path}/upload", data=evidence_args, headers=evidence_headers,
                files={"file": ("Тестовый дефектный акт.docx", word_evidence, DOCX_MIME)},
            ))

        external_defect = await upload_defect()
        assert (await upload_defect())["id"] == external_defect["id"]
        originals[(external_defect["id"], 1)] = word_evidence
        assert external_defect["scope_meta"]["equipment_ids"] == [unit_a]

        await db.refresh(order)
        assert order.customer_branch_id == branch_a.id and order.total_amount == AGREED_PRICE
        order.status = OrderStatus.CLOSED
        await db.commit()
        signed_act = pdf_bytes("Synthetic signed completion record TEST-1278")
        copied = response_json(await manager.post(
            f"/api/manager/docs/{completion_id}/file",
            data={"file_role": "signed_copy", "expected_version": "0"},
            headers={**headers, "Idempotency-Key": str(uuid4())},
            files={"file": ("Тестовый подписанный акт.pdf", signed_act, "application/pdf")},
        ))
        originals[(completion_id, 1)] = signed_act
        assert copied["external_files"][0]["role"] == "signed_copy"
        await db.refresh(full_act)
        assert full_act.render_snapshot == frozen and full_act.status == "issued"

        expected = {contract["id"], draft_a.id, draft_b.id, draft_c.id, completion_id, external_defect["id"]}
        all_docs = (await manager_get(docs_path, include_native=True))["items"]
        assert {row["id"] for row in all_docs} == expected
        assert [row["id"] for row in all_docs if row["doc_type"] == "act"] == [completion_id]
        by_id = {row["id"]: row for row in all_docs}
        unauthenticated = await manager.get(f"/api/manager/docs/{contract['id']}/download", params={"file_version": 1})
        assert unauthenticated.status_code in (401, 403)
        for (doc_id, version), expected_bytes in originals.items():
            assert by_id[doc_id]["external_files"][0]["checksum_sha256"] == sha256(expected_bytes).hexdigest()
            download = await manager.get(f"/api/manager/docs/{doc_id}/download", headers=headers, params={"file_version": version})
            assert download.status_code == 200 and download.content == expected_bytes
            assert download.headers["cache-control"] == "private, no-store"

        for site, ids in (
            (a, {draft_a.id, completion_id, external_defect["id"]}),
            (b, {draft_b.id, completion_id}),
            (c, {draft_c.id, completion_id}),
        ):
            site_docs = (await manager_get(docs_path, include_native=True, site_id=site["id"]))["items"]
            assert {row["id"] for row in site_docs} == ids
        equipment_docs = (await manager_get(docs_path, include_native=True, equipment_id=unit_b2))["items"]
        assert [row["id"] for row in equipment_docs] == [draft_b.id]
        accessible = success(await call(mcp, "list_order_documents", mcp_order))
        assert {row["document_id"] for row in accessible["items"]} == expected
        assert all(f"documentId={row['document_id']}" in row["manager_url"] for row in accessible["items"])
        b_docs = success(await call(mcp, "list_order_documents", {
            **mcp_order, "site_id": b["id"], "equipment_id": unit_b2, "document_type": "technical_inspection_act",
        }))
        assert [row["document_id"] for row in b_docs["items"]] == [draft_b.id]

    await db.refresh(line)
    assert line.price == AGREED_PRICE and line.quantity == 1
    assert await db.scalar(select(func.count()).select_from(Order)) == 1
    assert await db.scalar(select(func.count()).select_from(OrderProposal)) == 1
    assert await db.scalar(select(func.count()).select_from(OrderServiceLink)) == 1
    assert await db.scalar(select(func.count()).select_from(EquipmentServiceHistory)) == 0
