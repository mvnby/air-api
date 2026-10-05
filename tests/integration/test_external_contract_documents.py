from datetime import date, datetime
from io import BytesIO
from types import SimpleNamespace

import pytest

from core.config import settings
from models import OrderDocument, OrderStatus
from models.tenancy import TenantScope
from modules.documents.application import (
    DocumentContextSelection,
    ManagedDocumentService,
    NativeTemplatePlaceholderContract,
    NativeTemplateVersionService,
)
from modules.documents.domain import ActTerms
from modules.documents.infrastructure.renderers import TableBlockSpec
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)
from services.document_service import DocumentService, OrderDocumentsLockedError
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_document_context_builder import _seed_order
from tests.integration.test_managed_document_lifecycle import _template_docx


SYSTEM_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.mark.asyncio
async def test_external_contract_registers_number_and_date_without_a_file(
    db, monkeypatch
):
    order, _issuer, _selected, _alternative = await _seed_order(db)
    contract_date = datetime(2026, 9, 30)

    async def unexpected_upload(*_args, **_kwargs):
        raise AssertionError("registration without a file must not upload to Drive")

    monkeypatch.setattr(
        DocumentService, "_upload_document_file", staticmethod(unexpected_upload)
    )

    document = await DocumentService.register_external_contract(
        db,
        order_id=order.id,
        number="260930",
        contract_date=contract_date,
        tenant_scope=SYSTEM_SCOPE,
    )

    assert document.tenant_id == order.tenant_id
    assert document.doc_type == "contract"
    assert document.number == "260930"
    assert document.date == contract_date
    assert document.google_file_id == ""
    assert document.google_edit_url == ""
    await db.refresh(order)
    assert order.contract_date == contract_date

    with pytest.raises(ValueError, match="Дата договора обязательна"):
        await DocumentService.register_external_contract(
            db,
            order_id=order.id,
            number="260930",
            contract_date=None,
            tenant_scope=SYSTEM_SCOPE,
        )


@pytest.mark.asyncio
async def test_external_contract_registration_checks_tenant_and_closed_order(db):
    order, _issuer, _selected, _alternative = await _seed_order(db)

    with pytest.raises(ValueError, match="Order not found"):
        await DocumentService.register_external_contract(
            db,
            order_id=order.id,
            number="260930",
            contract_date=datetime(2026, 9, 30),
            tenant_scope=TenantScope(tenant_id=2, storefront_id=2),
        )

    order.status = OrderStatus.CLOSED
    db.add(order)
    await db.commit()
    with pytest.raises(OrderDocumentsLockedError):
        await DocumentService.register_external_contract(
            db,
            order_id=order.id,
            number="260930",
            contract_date=datetime(2026, 9, 30),
            tenant_scope=SYSTEM_SCOPE,
        )


@pytest.mark.asyncio
async def test_native_act_draft_uses_external_contract_number_and_date(db, tmp_path):
    order, issuer, _selected, _alternative = await _seed_order(db)
    external_contract = await DocumentService.register_external_contract(
        db,
        order_id=order.id,
        number="260930",
        contract_date=datetime(2026, 9, 30),
        tenant_scope=SYSTEM_SCOPE,
    )

    private = LocalPrivateAttachmentStorage(tmp_path / "external-contract-documents")
    template_storage = PrivateTemplateSourceStorage(private)
    template = await NativeTemplateVersionService.create_template(
        db,
        tenant_scope=SYSTEM_SCOPE,
        legal_entity_id=issuer.id,
        name="Акт по договору заказчика",
        doc_type="act",
    )
    version = await NativeTemplateVersionService.upload_native_docx_version(
        db,
        tenant_scope=SYSTEM_SCOPE,
        legal_entity_id=issuer.id,
        template_id=template.id,
        filename="Акт.docx",
        content=_template_docx(),
        placeholder_contract=NativeTemplatePlaceholderContract.create(
            field_catalog={
                "document.official_full_number",
                "customer.full_name",
            },
            table_blocks=(
                TableBlockSpec(
                    name="lines",
                    row_fields=frozenset(
                        {
                            "line.number",
                            "line.title",
                            "line.quantity",
                            "line.amount",
                        }
                    ),
                ),
            ),
        ),
        storage=template_storage,
    )
    await NativeTemplateVersionService.activate_version(
        db,
        tenant_scope=SYSTEM_SCOPE,
        legal_entity_id=issuer.id,
        template_id=template.id,
        version_id=version.id,
    )

    draft = await ManagedDocumentService.create_draft(
        db,
        tenant_scope=SYSTEM_SCOPE,
        selection=DocumentContextSelection(
            order_id=order.id,
            legal_entity_id=issuer.id,
            document_type="act",
            issue_date=date(2026, 10, 5),
            base_document_id=external_contract.id,
            act_terms=ActTerms(claims_status="none"),
        ),
        template_storage=template_storage,
    )

    assert draft.base_document_id == external_contract.id
    assert draft.render_snapshot["values"]["basis.number"] == "260930"
    assert draft.render_snapshot["values"]["basis.date"] == "30.09.2026"


def test_external_contract_photo_extensions_are_scoped_to_contract_uploads():
    assert DocumentService._validate_upload_file(
        SimpleNamespace(filename="Договор.JPG"), allow_images=True
    ) == ("Договор.JPG", ".jpg")
    assert DocumentService._validate_upload_file(
        SimpleNamespace(filename="Договор.jpeg"), allow_images=True
    ) == ("Договор.jpeg", ".jpeg")
    assert DocumentService._validate_upload_file(
        SimpleNamespace(filename="Договор.png"), allow_images=True
    ) == ("Договор.png", ".png")
    with pytest.raises(ValueError, match="PDF, DOC и DOCX"):
        DocumentService._validate_upload_file(
            SimpleNamespace(filename="договор.png")
        )
    with pytest.raises(ValueError, match="JPG, JPEG и PNG"):
        DocumentService._validate_upload_file(
            SimpleNamespace(filename="договор.gif"), allow_images=True
        )


@pytest.mark.asyncio
async def test_external_contract_photo_upload_uses_image_mime_type(db, monkeypatch):
    order, _issuer, _selected, _alternative = await _seed_order(db)
    captured = {}

    class FakeUpload:
        filename = "Договор заказчика.jpeg"
        content_type = "image/jpeg"

        async def read(self):
            return b"jpeg photo"

    class FakeGoogleService:
        def upload_file(self, *, file_path, filename, mime_type, folder_id):
            captured.update(
                filename=filename,
                mime_type=mime_type,
                folder_id=folder_id,
            )
            return "uploaded-customer-contract-photo"

    from services import document_service

    monkeypatch.setattr(
        document_service, "get_google_service", lambda: FakeGoogleService()
    )
    document = await DocumentService.register_external_contract(
        db,
        order_id=order.id,
        number="260930",
        contract_date=datetime(2026, 9, 30),
        file=FakeUpload(),
        tenant_scope=SYSTEM_SCOPE,
    )

    assert document.google_file_id == "uploaded-customer-contract-photo"
    assert captured["filename"].endswith(".jpeg")
    assert captured["mime_type"] == "image/jpeg"
    assert captured["folder_id"]


@pytest.mark.parametrize(
    ("source_filename", "source_mime_type"),
    (
        ("Договор 260930.jpg", "image/jpeg"),
        ("Договор 260930.pdf", "application/pdf"),
        (
            "Договор 260930.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ),
)
@pytest.mark.asyncio
async def test_external_contract_file_download_preserves_original_and_mime_type(
    async_client,
    db,
    monkeypatch,
    source_filename,
    source_mime_type,
):
    order, _issuer, _selected, _alternative = await _seed_order(db)
    document = OrderDocument(
        tenant_id=1,
        order_id=order.id,
        doc_type="contract",
        number="260930",
        date=datetime(2026, 9, 30),
        google_file_id="customer-contract-photo",
        google_edit_url="https://drive.google.com/file/d/customer-contract-photo/view",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    original = b"original customer contract photo"

    class FakeGoogleService:
        def get_file_metadata(self, file_id):
            assert file_id == "customer-contract-photo"
            return {"name": source_filename, "mimeType": source_mime_type}

        def download_file(self, file_id):
            assert file_id == "customer-contract-photo"
            return BytesIO(original)

    from services import document_service

    monkeypatch.setattr(
        document_service, "get_google_service", lambda: FakeGoogleService()
    )
    login = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login.status_code == 200

    response = await async_client.get(
        f"/api/manager/docs/{document.id}/download",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(source_mime_type)
    assert response.content == original
    assert source_filename.rsplit(".", 1)[-1] in response.headers[
        "content-disposition"
    ]
