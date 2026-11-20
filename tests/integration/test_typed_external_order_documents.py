from datetime import date, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfWriter
from sqlalchemy import func, select

from core.command_actor import CommandActor
from core.security import create_access_token
from models import OrderDocument, OrderDocumentExternalFile, OrderStatus, StaffUser, TenantMembership
from models.tenancy import TenantScope
from modules.documents.application.external_order_documents import (
    ExternalDocumentConflictError,
    ExternalDocumentFileSource,
    ExternalOrderDocumentPayload,
    ExternalOrderDocumentService,
)
from modules.documents.application.open_contract_basis import resolve_native_basis
from services.order_delete_command_service import OrderDeleteCommandService, OrderHasExternalEvidence
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict
from tests.integration.test_document_context_builder import _seed_order


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
SERVICE = ExternalOrderDocumentService


def _pdf(label):
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.add_metadata({"/Title": label})
    writer.write(output)
    return output.getvalue()


async def _staff(db):
    staff = StaffUser(username="external-evidence-staff", display_name="Test Manager",
                      status="active", roles=["manager"], primary_role="manager")
    db.add(staff)
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=staff.id, role="manager", status="active"))
    await db.commit()
    return staff, CommandActor(staff.id, staff.username, SCOPE)


def _contract():
    return ExternalOrderDocumentPayload(document_type="contract", number="EXT-01", document_date=date(2026, 11, 19))


@pytest.mark.asyncio
async def test_private_versions_replay_and_explicit_contract_basis(db, tmp_path):
    order, issuer, _selected, _alternative = await _seed_order(db)
    previous_contract_date = order.contract_date
    _user, actor = await _staff(db)
    storage = LocalPrivateAttachmentStorage(tmp_path / "evidence")
    original = _pdf("first")
    file = ExternalDocumentFileSource.from_bytes(original, "договор.pdf", "application/pdf")
    key = str(uuid4())
    options = dict(actor=actor, order_id=order.id, payload=_contract(), idempotency_key=key, source=file, storage=storage)
    created = await SERVICE.create(db, **options)
    replay = await SERVICE.create(db, **options)
    assert replay.replayed and replay.value == created.value
    doc_id = created.value.document_id
    assert await db.scalar(select(func.count()).select_from(OrderDocument)) == 1

    changed_request = {**options, "source": ExternalDocumentFileSource.from_bytes(_pdf("other"), "договор.pdf", "application/pdf")}
    with pytest.raises(PublicWriteIdempotencyConflict):
        await SERVICE.create(db, **changed_request)
    with pytest.raises(LookupError):
        await SERVICE.create(db, **{**options, "actor": CommandActor(actor.staff_user_id, actor.username, TenantScope(2, 2))})

    await db.refresh(order)
    assert order.contract_date == previous_contract_date
    native_basis = dict(order=order, issuer_id=issuer.id, document_type="act", issue_date=date(2026, 11, 20), base_customer_contract_id=None)
    assert await resolve_native_basis(db, **native_basis, base_document_id=None) == (None, None)
    linked, _entry = await resolve_native_basis(db, **native_basis, base_document_id=doc_id)
    assert (linked.origin, linked.number, linked.date, linked.status) == (
        "external_upload", "EXT-01", datetime(2026, 11, 19), None,
    )

    second = _pdf("second")
    revision = await SERVICE.attach(
        db, actor=actor, document_id=doc_id, file_role="original", expected_version=1,
        idempotency_key=str(uuid4()), storage=storage,
        source=ExternalDocumentFileSource.from_bytes(second, "", ""),
    )
    assert revision.value.file_version == 2
    with pytest.raises(ExternalDocumentConflictError, match="Версия файла изменилась"):
        await SERVICE.attach(
            db, actor=actor, document_id=doc_id, file_role="original", expected_version=1,
            idempotency_key=str(uuid4()), source=file, storage=storage,
        )
    old_file, old_bytes = await SERVICE.read_file(db, tenant_scope=SCOPE, document_id=doc_id, version=1, storage=storage)
    new_file, new_bytes = await SERVICE.read_file(db, tenant_scope=SCOPE, document_id=doc_id, storage=storage)
    assert (old_file.filename, old_bytes) == ("договор.pdf", original)
    assert (new_file.filename, new_bytes) == ("document.pdf", second)
    assert old_file.storage_key != new_file.storage_key
    with pytest.raises(LookupError):
        await SERVICE.read_file(db, tenant_scope=TenantScope(2, 2), document_id=doc_id, version=1, storage=storage)
    assert await db.scalar(select(func.count()).select_from(OrderDocumentExternalFile)) == 2
    with pytest.raises(OrderHasExternalEvidence):
        await OrderDeleteCommandService.delete_order(db, order.id, tenant_scope=SCOPE)


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_closed_order_can_receive_signed_pdf_without_mutating_native_issue(db, tmp_path, legacy):
    order, issuer, selected, _alternative = await _seed_order(db)
    _user, actor = await _staff(db)
    issued = OrderDocument(
        tenant_id=None if legacy else 1,
        order_id=order.id, proposal_id=selected.id, doc_type="act", number="ACT-01",
        date=datetime(2026, 11, 20), status=None if legacy else "issued",
        internal_reference=None if legacy else "issued-act-ref",
        legal_entity_id=None if legacy else issuer.id,
        render_snapshot={"values": {"totals.amount": "320.00"}},
    )
    order.status = OrderStatus.CLOSED
    db.add_all([issued, order])
    await db.commit()
    storage = LocalPrivateAttachmentStorage(tmp_path / "evidence")
    data = _pdf("customer signed")
    file = ExternalDocumentFileSource.from_bytes(data, "подписано.pdf", "application/pdf")
    with pytest.raises(ExternalDocumentConflictError):
        await SERVICE.create(db, actor=actor, order_id=order.id, payload=_contract(),
                             idempotency_key=str(uuid4()), source=file, storage=storage)
    with pytest.raises(ExternalDocumentConflictError):
        await SERVICE.attach(db, actor=actor, document_id=issued.id, file_role="original", expected_version=0,
                             idempotency_key=str(uuid4()), source=file, storage=storage)
    attach = dict(actor=actor, document_id=issued.id, file_role="signed_copy", expected_version=0,
                  idempotency_key=str(uuid4()), source=file, storage=storage)
    if legacy:
        foreign_actor = CommandActor(actor.staff_user_id, actor.username, TenantScope(2, 2))
        with pytest.raises(LookupError):
            await SERVICE.attach(db, **{**attach, "actor": foreign_actor})
        await db.refresh(issued)
        assert issued.tenant_id is None
    saved = await SERVICE.attach(db, **attach)
    assert saved.value.file_version == 1
    assert (await SERVICE.attach(db, **attach)).replayed
    await db.refresh(issued)
    assert issued.tenant_id == order.tenant_id
    assert issued.status == (None if legacy else "issued")
    assert issued.render_snapshot == {"values": {"totals.amount": "320.00"}}
    assert issued.google_file_id is None and issued.origin is None
    assert await SERVICE.read_file(db, tenant_scope=SCOPE, document_id=issued.id, storage=storage) is None
    record, stored = await SERVICE.read_file(db, tenant_scope=SCOPE, document_id=issued.id, version=1, storage=storage)
    assert record.role == "signed_copy" and stored == data


@pytest.mark.asyncio
async def test_manager_typed_upload_rejects_fake_pdf_and_downloads_unchanged_original(async_client, db, tmp_path, monkeypatch):
    order, _issuer, _selected, _alternative = await _seed_order(db)
    user, _actor = await _staff(db)
    auth_token = create_access_token({"sub": user.username, "staff_user_id": user.id,
                                     "auth_source": "staff_password", "auth_version": user.auth_version})
    base_headers = {"Authorization": f"Bearer {auth_token}"}
    headers = {**base_headers, "Idempotency-Key": str(uuid4())}
    storage = LocalPrivateAttachmentStorage(tmp_path / "evidence")
    monkeypatch.setattr("modules.documents.application.external_order_documents.get_private_attachment_storage", lambda *args: storage)
    docs = f"/api/manager/orders/{order.id}/documents"
    unsigned = await async_client.post(f"{docs}/external-contract", headers=headers, data={
        "number": "EXT-01", "contract_date": "2026-11-19T00:00:00", "external_status": "signed",
    })
    assert unsigned.status_code == 400, unsigned.text
    assert "исходный файл" in unsigned.json()["detail"]["message"]
    attributes = {"document_type": "contract", "number": "EXT-01", "document_date": "2026-11-19", "external_status": "signed"}
    bad = await async_client.post(f"{docs}/upload", data=attributes, headers=headers,
                                  files={"file": ("договор.pdf", b"not a PDF", "application/pdf")})
    assert bad.status_code == 400, bad.text
    assert (await async_client.get(docs, headers=base_headers)).json()["items"] == []
    content = _pdf("manager")
    from services import external_document_scan

    original_scan = external_document_scan.scan_external_document

    async def unavailable_scan(_content):
        raise external_document_scan.ExternalDocumentScanUnavailable("Антивирусная проверка недоступна.")

    monkeypatch.setattr(external_document_scan, "scan_external_document", unavailable_scan)
    unavailable = await async_client.post(f"{docs}/upload", data=attributes, headers=headers,
                                          files={"file": ("договор.pdf", content, "application/pdf")})
    assert unavailable.status_code == 503, unavailable.text
    assert (await async_client.get(docs, headers=base_headers)).json()["items"] == []
    assert not list((tmp_path / "evidence").rglob("*.pdf"))
    monkeypatch.setattr(external_document_scan, "scan_external_document", original_scan)
    uploaded = await async_client.post(f"{docs}/upload", data=attributes, headers=headers,
                                       files={"file": ("договор.pdf", content, "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    item = uploaded.json()
    assert (item["origin"], item["status"], item["external_status"], item["file_version"]) == ("external_upload", None, "signed", 1)
    assert item["external_files"][0]["filename"] == "договор.pdf"
    assert "storage_key" not in item["external_files"][0]
    assert (await async_client.get(f"{docs}?document_type=act", headers=base_headers)).json()["items"] == []
    download_url = f"/api/manager/docs/{item['id']}/download"
    downloaded = await async_client.get(download_url, headers=base_headers)
    assert downloaded.status_code == 200 and downloaded.content == content
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert (await async_client.get(f"{download_url}?file_version=2", headers=base_headers)).status_code == 404
    act = await async_client.post(
        f"{docs}/upload", headers={**base_headers, "Idempotency-Key": str(uuid4())},
        data={"document_type": "act", "number": "А-1", "document_date": "2026-11-20", "base_document_id": item["id"]},
        files={"file": ("акт.pdf", _pdf("act"), "application/pdf")},
    )
    assert act.status_code == 200, act.text
    assert (act.json()["base_document_id"], act.json()["base_document_number"]) == (item["id"], "EXT-01")
    filtered = await async_client.get(f"{docs}?document_type=act", headers=base_headers)
    assert filtered.status_code == 200, filtered.text
    assert [(row["base_document_id"], row["base_document_number"]) for row in filtered.json()["items"]] == [(item["id"], "EXT-01")]


@pytest.mark.asyncio
async def test_typed_word_act_preserves_scope_and_rejects_equipment_from_another_site(db, tmp_path):
    from docx import Document
    from models.order_site import OrderSite
    from schemas_order_sites import OrderSiteAddPayload, OrderSiteEquipmentLinkPayload, OrderSiteNewEquipment
    from services.order_site_service import OrderSiteService

    order, _issuer, selected, _alternative = await _seed_order(db)
    _user, actor = await _staff(db)
    storage = LocalPrivateAttachmentStorage(tmp_path / "evidence")

    async def add_site(title):
        result = await OrderSiteService.add_site(
            db, actor, order.id, OrderSiteAddPayload(title=title, address=f"Тестовый адрес {title}"),
            idempotency_key=str(uuid4()),
        )
        return result.value

    site_a = await add_site("A")
    site_b = await add_site("B")
    linked = await OrderSiteService.link_equipment(
        db, actor, order.id, site_a.id,
        OrderSiteEquipmentLinkPayload(expected_version=site_a.version,
                                      equipment=OrderSiteNewEquipment(display_name="Кондиционер без шильдика")),
        idempotency_key=str(uuid4()),
    )
    equipment_id = linked.value.equipment.equipment_id
    registered = await SERVICE.create(db, actor=actor, order_id=order.id, payload=_contract(), idempotency_key=str(uuid4()))
    b_id = registered.value.document_id
    docx = Document()
    docx.add_paragraph("Рекомендован поиск утечки хладагента. Ремонт ещё не выполнен.")
    output = BytesIO()
    docx.save(output)
    data = output.getvalue()
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    payload = ExternalOrderDocumentPayload(
        document_type="defect_act", number="DEF-01", document_date=date(2026, 11, 20),
        site_id=site_a.id, equipment_ids=[equipment_id], base_document_id=b_id, proposal_id=selected.id,
    )
    command = dict(actor=actor, order_id=order.id, idempotency_key=str(uuid4()),
                   source=ExternalDocumentFileSource.from_bytes(data, "Дефектный акт.docx", mime), storage=storage)
    with pytest.raises(ValueError, match="не всё|Не всё"):
        await SERVICE.create(db, **command, payload=payload.model_copy(update={"site_id": site_b.id}))
    result = await SERVICE.create(db, **command, payload=payload)
    document = await SERVICE.get_document(db, SCOPE, result.value.document_id)
    assert (document.scope_title, document.scope_address, document.base_document_id) == ("A", "Тестовый адрес A", b_id)
    assert document.scope_meta["equipment_ids"] == [equipment_id]
    assert document.scope_meta["equipment"][0]["display_name"] == "Кондиционер без шильдика"
    assert not document.scope_meta["equipment"][0]["serial"]
    site_record = await db.get(OrderSite, site_a.id)
    site_record.address = "Новый тестовый адрес"
    await db.commit()
    await db.refresh(document)
    assert document.scope_address == "Тестовый адрес A"
    stored, content = await SERVICE.read_file(db, tenant_scope=SCOPE, document_id=document.id, storage=storage)
    assert (stored.mime_type, content) == (mime, data)
    await db.refresh(order)
    assert float(order.total_amount) == 1_400


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_act", ["legacy", "native_unscoped", "native_scoped"])
async def test_signed_external_act_cannot_duplicate_effective_coverage(db, existing_act):
    from modules.documents.application.order_completion_coverage import COVERAGE_KEY

    order, issuer, selected, _alternative = await _seed_order(db)
    _user, actor = await _staff(db)
    db.add(OrderDocument(
        tenant_id=1, order_id=order.id, proposal_id=selected.id, doc_type="act", number="NATIVE-ACT-1",
        date=datetime(2026, 11, 20), status=None if existing_act == "legacy" else "issued",
        internal_reference=None if existing_act == "legacy" else "act-ref",
        legal_entity_id=issuer.id,
        render_snapshot={"meta": {COVERAGE_KEY: {"schema_version": 1}}} if existing_act == "native_scoped" else None,
    ))
    await db.commit()

    async def unexpected_load():
        pytest.fail("The commercial guard must reject the upload before fetching any file")

    with pytest.raises(ExternalDocumentConflictError, match="уже оформлен акт"):
        await SERVICE.create(
            db, actor=actor, order_id=order.id,
            payload=ExternalOrderDocumentPayload(document_type="act", number="EXT-ACT-1",
                                                 document_date=date(2026, 11, 20), external_status="signed"),
            source=ExternalDocumentFileSource("акт.pdf", "application/pdf", "synthetic-file-id", unexpected_load),
            idempotency_key=str(uuid4()),
        )
    assert await db.scalar(select(func.count()).select_from(OrderDocument)) == 1


@pytest.mark.asyncio
async def test_signed_external_act_blocks_second_closure_but_keeps_evidence_and_replays(db, tmp_path):
    from modules.documents.application.errors import ManagedDocumentConflictError
    from modules.documents.application.order_completion_coverage import ensure_legacy_act_write_allowed

    order, _issuer, _selected, _alternative = await _seed_order(db)
    _user, actor = await _staff(db)
    order_id, original_total = order.id, order.total_amount
    storage = LocalPrivateAttachmentStorage(tmp_path / "evidence")
    received = ExternalOrderDocumentPayload(document_type="act", number="EXT-ACT-1", document_date=date(2026, 11, 20))
    command = dict(
        actor=actor, order_id=order_id, storage=storage,
        source=ExternalDocumentFileSource.from_bytes(_pdf("External completion"), "акт.pdf", "application/pdf"),
    )

    await SERVICE.create(db, **command, payload=received, idempotency_key=str(uuid4()))
    await ensure_legacy_act_write_allowed(db, order_id)
    signed = received.model_copy(update={"external_status": "signed"})
    signed_key = str(uuid4())
    first = await SERVICE.create(db, **command, payload=signed, idempotency_key=signed_key)
    replay = await SERVICE.create(db, **command, payload=signed, idempotency_key=signed_key)
    assert replay.replayed and first.value == replay.value

    with pytest.raises(ExternalDocumentConflictError, match="уже оформлен акт"):
        await SERVICE.create(db, **command, payload=signed, idempotency_key=str(uuid4()))
    with pytest.raises(ManagedDocumentConflictError, match="подписанный внешний акт"):
        await ensure_legacy_act_write_allowed(db, order_id)
    await SERVICE.create(db, **command, payload=received, idempotency_key=str(uuid4()))
    assert await db.scalar(select(func.count()).select_from(OrderDocument).where(
        OrderDocument.order_id == order_id, OrderDocument.external_status == "signed",
    )) == 1
    await db.refresh(order)
    assert order.total_amount == original_total
