"""PostgreSQL and native DOCX coverage for technical documents in an ordinary service order."""

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

from docx import Document
import pytest
from sqlmodel import func, select

from core.config import settings
from models import (
    Customer, CustomerBranch, CustomerEquipment, CustomerType, DocumentLegalEntity, EquipmentComponent,
    EquipmentServiceHistory, Order, OrderDocument, OrderProposal, OrderServiceLink, OrderStatus,
    StaffUser, TenantMembership,
)
from models.order_inspection import OrderInspectionRevision
from models.order_site import OrderSite, OrderSiteEquipment
from models.tenancy import TenantScope
from modules.documents.application.lifecycle_service import ManagedDocumentService
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from services.document_service import DocumentService
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_managed_document_lifecycle import FakePdfConverter
from tests.integration.test_manager_access_permissions import _headers


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


async def seed(db):
    customer = Customer(tenant_id=1, type=CustomerType.company, name="Тестовый заказчик", phone="")
    issuer = DocumentLegalEntity(tenant_id=1, slug="diagnostics-issuer", display_name="Тестовый исполнитель")
    staff = StaffUser(username="diagnostic-test-manager", display_name="Тестовый менеджер", roles=["manager"], primary_role="manager")
    db.add_all([customer, issuer, staff])
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=staff.id, role="manager"))
    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id,
                  workflow_type="service_work", status=OrderStatus.EXECUTION)
    db.add(order)
    await db.flush()
    proposal = OrderProposal(order_id=order.id, name="Диагностика с логистикой", is_selected=True)
    db.add(proposal)
    await db.flush()
    line = OrderServiceLink(order_id=order.id, proposal_id=proposal.id,
                            title="Диагностика трёх объектов с логистикой", quantity=1, price=Decimal("900"))
    db.add(line)
    sites = []
    units = []
    for label, count in (("A", 1), ("B", 2), ("C", 1)):
        branch = CustomerBranch(customer_id=customer.id, name=f"Объект {label}", delivery_address=f"Тестовый адрес {label}")
        db.add(branch)
        await db.flush()
        site = OrderSite(order_id=order.id, customer_id=customer.id, customer_branch_id=branch.id,
                         title=branch.name, address=branch.delivery_address)
        db.add(site)
        await db.flush()
        sites.append(site)
        for index in range(count):
            unit = CustomerEquipment(customer_id=customer.id, customer_branch_id=branch.id,
                                     display_name=f"Установка {label}{index + 1}")
            db.add(unit)
            await db.flush()
            db.add(OrderSiteEquipment(order_id=order.id, site_id=site.id, equipment_id=unit.id, role="diagnostic"))
            units.append(unit)
    db.add_all([
        EquipmentComponent(equipment_id=units[1].id, component_type="indoor_unit", model="TEST-B1-IN"),
        EquipmentComponent(equipment_id=units[1].id, component_type="outdoor_unit", model="TEST-B1-OUT"),
        EquipmentComponent(equipment_id=units[3].id, component_type="drain_pump", title="Дренажный насос"),
    ])
    await db.commit()
    contract = await DocumentService.register_external_contract(
        db, order_id=order.id, number="ДОГ-123", contract_date=datetime(2026, 11, 1), tenant_scope=SCOPE,
    )
    return order, issuer, contract, sites, units, _headers(staff), proposal, line


def inspection_payload(status, facts, **extra):
    return {"expected_version": 0, "idempotency_key": str(uuid4()), "status": status, "facts": facts, **extra}


def site_path(order, site):
    return f"/api/manager/orders/{order.id}/sites/{site.id}"


def inspection_path(order, site, unit):
    return f"{site_path(order, site)}/equipment/{unit.id}/inspection"


def act_payload(issuer, contract, site, units, *, kind="technical_inspection_act", **extra):
    return {
        "idempotency_key": str(uuid4()), "expected_site_version": site.version, "document_type": kind,
        "inspections": [{"equipment_id": unit.id, "expected_version": 1} for unit in units],
        "legal_entity_id": issuer.id, "base_document_id": contract.id, "issue_date": "2026-11-20", **extra,
    }


@pytest.mark.asyncio
async def test_one_service_order_retains_three_scoped_act_snapshots(async_client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SERVICE_ATTACHMENT_LOCAL_DIR", str(tmp_path))
    order, issuer, contract, (a, b, c), (unit_a, unit_b1, unit_b2, unit_c), headers, proposal, line = await seed(db)
    a_payload = inspection_payload("defect_found", "Зафиксирован существенный недостаток хладагента.",
                                   recommendations="Отдельно согласовать поиск и устранение утечки.")
    a_path = inspection_path(order, a, unit_a)
    empty = await async_client.get(a_path, headers=headers)
    assert empty.status_code == 200 and empty.json()["current_version"] == 0 and empty.json()["inspection"] is None
    for site, unit, payload in (
        (a, unit_a, a_payload),
        (b, unit_b1, inspection_payload("no_defect_found", "Установка работала штатно.",
                                        trial_result="Замечаний при запуске нет.", event_history="Редкие ошибки не повторились.")),
        (b, unit_b2, inspection_payload("no_defect_found", "При проверке дефект не выявлен.")),
        (c, unit_c, inspection_payload("restored", "После очистки отвод конденсата восстановлен.",
                                      performed_actions="Очищен дренажный насос в рамках диагностики.")),
    ):
        response = await async_client.put(inspection_path(order, site, unit), headers=headers, json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["result"]["version"] == 1
    replay = await async_client.put(a_path, headers=headers, json=a_payload)
    assert replay.status_code == 200 and replay.json()["replayed"]
    stale = await async_client.put(a_path, headers=headers, json={**a_payload, "idempotency_key": str(uuid4())})
    assert stale.status_code == 409
    wrong_site = await async_client.get(inspection_path(order, a, unit_b1), headers=headers)
    assert wrong_site.status_code in (400, 404)

    drafts = []
    for site, units, kind in (
        (a, [unit_a], "defect_act"),
        (b, [unit_b1, unit_b2], "technical_inspection_act"),
        (c, [unit_c], "technical_inspection_act"),
    ):
        path = f"{site_path(order, site)}/technical-acts"
        command = act_payload(issuer, contract, site, units, kind=kind)
        response = await async_client.post(path, headers=headers, json=command)
        assert response.status_code == 200, response.text
        uid = response.json()["result"]["document_id"]
        duplicate = await async_client.post(path, headers=headers, json=command)
        assert duplicate.json()["replayed"] and duplicate.json()["result"]["document_id"] == uid
        draft = await db.get(OrderDocument, uid)
        assert draft.order_id == order.id and draft.status == "draft" and draft.official_number is None
        assert draft.base_document_id == contract.id and draft.proposal_id == proposal.id
        assert draft.scope_meta["site_ids"] == [site.id]
        assert draft.scope_meta["equipment_ids"] == [unit.id for unit in units]
        assert draft.render_snapshot["values"]["basis.number"] == contract.number
        assert list(draft.render_snapshot["table_rows"]) == ["inspections"]
        assert "totals.amount" not in draft.render_snapshot["values"]
        drafts.append(draft)
    wrong_scope = await async_client.post(f"{site_path(order, b)}/technical-acts", headers=headers,
                                        json=act_payload(issuer, contract, b, [unit_a, unit_b1]))
    assert wrong_scope.status_code in (400, 404)
    no_defect = await async_client.post(f"{site_path(order, b)}/technical-acts", headers=headers,
                                       json=act_payload(issuer, contract, b, [unit_b1], kind="defect_act"))
    assert no_defect.status_code == 400

    draft_a, draft_b, draft_c = drafts
    assert draft_a.render_snapshot["table_rows"]["inspections"][0]["inspection.performed_actions"] == "—"
    assert "Отдельно согласовать" in draft_a.render_snapshot["table_rows"]["inspections"][0]["inspection.recommendations"]
    assert "Очищен дренажный насос" in draft_c.render_snapshot["table_rows"]["inspections"][0]["inspection.performed_actions"]
    storage = LocalPrivateAttachmentStorage(tmp_path)
    artifact_storage = PrivateDocumentArtifactStorage(storage)
    issued = await ManagedDocumentService.issue(
        db, tenant_scope=SCOPE, document_id=draft_b.id,
        template_storage=PrivateTemplateSourceStorage(storage), artifact_storage=artifact_storage,
        pdf_converter=FakePdfConverter(),
    )
    assert issued.document.status == "issued" and issued.document.sent_at is None
    artifact = next(item for item in issued.artifacts if item.kind == "rendered_docx")
    content = await artifact_storage.read(ManagedDocumentService.stored_artifact(artifact))
    rendering = Document(BytesIO(content))
    rows = [row.cells[0].text for row in rendering.tables[0].rows]
    assert len(rows) == 2 and "TEST-B1-OUT" in rows[0] and "Установка B2" in rows[1]
    assert "Редкие ошибки не повторились" in rows[0] and "Установка A1" not in rows[0]
    frozen = deepcopy(issued.document.render_snapshot)
    unit_b1.model = "Паспорт обновлён"
    db.add(unit_b1)
    await db.commit()
    changed = await async_client.put(inspection_path(order, b, unit_b1), headers=headers,
                                     json=inspection_payload("inconclusive", "Повторная проверка", expected_version=1))
    assert changed.status_code == 200 and changed.json()["result"]["version"] == 2
    original = await async_client.get(inspection_path(order, b, unit_b1), headers=headers, params={"version": 1})
    assert original.json()["inspection"]["status"] == "no_defect_found" and original.json()["current_version"] == 2
    await db.refresh(draft_b)
    assert draft_b.render_snapshot == frozen
    await db.refresh(line)
    assert line.price == Decimal("900") and line.quantity == 1
    assert await db.scalar(select(func.count()).select_from(Order)) == 1
    assert await db.scalar(select(func.count()).select_from(OrderServiceLink)) == 1
    assert await db.scalar(select(func.count()).select_from(EquipmentServiceHistory)) == 0
    assert await db.scalar(select(func.count()).select_from(OrderInspectionRevision)) == 5

    stale_act = await async_client.post(f"{site_path(order, b)}/technical-acts", headers=headers,
                                       json=act_payload(issuer, contract, b, [unit_b1]))
    assert stale_act.status_code == 409
    unit_b1.is_archived = True
    db.add(unit_b1)
    await db.commit()
    archived_command = inspection_payload("inconclusive", "Не должно сохраниться", expected_version=2)
    archived = await async_client.put(inspection_path(order, b, unit_b1), headers=headers, json=archived_command)
    assert archived.status_code == 409 and "в архиве" in archived.text
    previous = await async_client.get(inspection_path(order, b, unit_b1), headers=headers, params={"version": 1})
    assert previous.status_code == 200 and previous.json()["inspection"]["version"] == 1
    archived_act = await async_client.post(
        f"{site_path(order, b)}/technical-acts", headers=headers, json=act_payload(
            issuer, contract, b, [unit_b1], inspections=[{"equipment_id": unit_b1.id, "expected_version": 2}],
        ),
    )
    assert archived_act.status_code == 409 and "в архиве" in archived_act.text
    deletion = await async_client.delete(f"/api/manager/orders/{order.id}", headers=headers)
    assert deletion.status_code == 409 and "осмотрами" in deletion.text
    order.status = OrderStatus.CLOSED
    db.add(order)
    await db.commit()
    closed = await async_client.put(a_path, headers=headers,
                                     json=inspection_payload("defect_found", "Уточнение", expected_version=1))
    assert closed.status_code == 409
