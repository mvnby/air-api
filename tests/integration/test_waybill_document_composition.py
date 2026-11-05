from dataclasses import replace
from datetime import date
from io import BytesIO

import pytest
from docx import Document
from docx.shared import Cm
from sqlmodel import select

from models import OrderDocument, OrderProductLink, Product
from models.tenancy import TenantScope
from modules.documents.application import (
    ManagedDocumentService,
    NativeTemplateVersionService,
)
from modules.documents.application.context_builder import (
    DocumentContextBuilder,
    DocumentContextError,
    DocumentContextSelection,
)
from modules.documents.application.draft_mutations import (
    ManagedDocumentDraftMutationService,
)
from modules.documents.domain import TransportTerms
from modules.documents.application.native_template_discovery import (
    discover_native_placeholder_contract,
)
from modules.documents.domain.waybill_composition import (
    WaybillComponent,
    WaybillComposition,
    WaybillLineSelection,
)
from modules.documents.infrastructure.artifact_storage import (
    PrivateDocumentArtifactStorage,
)
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_document_context_builder import _seed_order
from tests.integration.test_managed_document_lifecycle import FakePdfConverter

SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


async def seeded_waybill(db):
    order, issuer, selected, other = await _seed_order(db)
    product = await db.scalar(
        select(OrderProductLink).where(OrderProductLink.proposal_id == selected.id)
    )
    product.quantity, product.price, product.title_snapshot = 1, 7400, "Система Atlas"
    product.logistics_components = None
    db.add(
        OrderDocument(
            tenant_id=1,
            legal_entity_id=issuer.id,
            order_id=order.id,
            proposal_id=selected.id,
            doc_type="contract",
            status="issued",
            internal_reference="doc_composition_basis",
            official_number="001",
            official_series="Д-",
            official_period_key="2026",
            official_date=date(2026, 6, 1),
            number="Д-2026-001",
        )
    )
    await db.commit()
    return order, issuer, selected, other, product


def component(title, price, count=1, country=""):
    return WaybillComponent(
        title=title,
        country=country,
        unit="шт.",
        quantity_per_parent=count,
        unit_price=price,
    )


def document_selection(kind, order, issuer, selected, revision, product, parts):
    return DocumentContextSelection(
        order_id=order.id,
        document_type=kind,
        legal_entity_id=issuer.id,
        issue_date=date(2026, 11, 6),
        proposal_id=selected.id,
        waybill_composition=WaybillComposition(
            source_revision=revision,
            lines=[
                WaybillLineSelection(order_product_line_id=product.id, components=parts)
            ],
        ),
    )


def test_catalog_revision_is_required_and_component_prices_are_exact():
    with pytest.raises(ValueError):
        component("Блок", "0.003")
    with pytest.raises(ValueError):
        component("Блок", "-0.01")
    with pytest.raises(ValueError):
        component("", "100")
    with pytest.raises(ValueError):
        component("Блок", "100", 0)


@pytest.mark.asyncio
async def test_waybill_source_endpoint_scopes_order_and_proposal(async_client, db):
    from tests.integration.test_consumer_equipment_defaults_api import (
        _auth_headers,
        _seed_defaults_order,
    )

    (
        order,
        foreign_site,
        foreign_tenant,
        selected,
        other,
        *_,
    ) = await _seed_defaults_order(db)
    headers = await _auth_headers(async_client)

    async def get(order_id, proposal_id):
        return await async_client.get(
            f"/api/manager/document-system/orders/{order_id}/waybill-composition",
            params={"proposal_id": proposal_id},
            headers=headers,
        )

    source = await get(order.id, selected.id)
    assert source.status_code == 200, source.text
    alternate = await get(order.id, other.id)
    assert source.json()["source_revision"] != alternate.json()["source_revision"]
    assert {
        line["order_product_line_id"] for line in source.json()["lines"]
    }.isdisjoint(line["order_product_line_id"] for line in alternate.json()["lines"])
    assert (await get(foreign_site.id, selected.id)).status_code == 404
    assert (await get(foreign_tenant.id, selected.id)).status_code == 404
    assert (await get(order.id, 999999)).status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["tn2", "ttn1"])
async def test_waybill_printed_rows_belong_only_to_draft(db, tmp_path, kind):
    order, issuer, selected, _, product = await seeded_waybill(db)
    if kind == "ttn1":
        product.quantity, product.price = 2, 2470
        await db.commit()
    catalog = await db.get(Product, product.product_id)
    catalog.specs = {}
    await db.commit()
    source = await DocumentContextBuilder.waybill_source(
        db, order_id=order.id, tenant_scope=SCOPE, proposal_id=selected.id
    )
    assert source.lines[0].country == ""
    private = LocalPrivateAttachmentStorage(tmp_path)
    storage, artifacts = (
        PrivateTemplateSourceStorage(private),
        PrivateDocumentArtifactStorage(private),
    )
    template = await NativeTemplateVersionService.create_template(
        db,
        tenant_scope=SCOPE,
        legal_entity_id=issuer.id,
        name="Проверка печати накладной",
        doc_type=kind,
    )
    doc = Document()
    doc.styles["Normal"].font.name = "DejaVu Sans"
    doc.add_paragraph("Накладная № {{ document.official_full_number }}")
    table = doc.add_table(rows=2, cols=5)
    table.style, table.autofit = "Table Grid", False
    for column, width in zip(table.columns, (5.7, 2.6, 2.5, 2.7, 3)):
        column.width = Cm(width)
        for cell in column.cells:
            cell.width = Cm(width)
    for cell, title in zip(
        table.rows[0].cells, ("Наименование", "Кол-во", "Цена", "Сумма", "Страна")
    ):
        cell.text = title
    for cell, field in zip(
        table.rows[1].cells,
        (
            "{{ lines }}{{ line.title }}",
            "{{ line.quantity }}",
            "{{ line.unit_price }}",
            "{{ line.amount }}",
            "{{ line.country }}",
        ),
    ):
        cell.text = field
    doc.add_paragraph("Итого {{ totals.amount }} BYN")
    output = BytesIO()
    doc.save(output)
    data = output.getvalue()
    version = await NativeTemplateVersionService.upload_native_docx_version(
        db,
        tenant_scope=SCOPE,
        legal_entity_id=issuer.id,
        template_id=template.id,
        filename="waybill.docx",
        content=data,
        storage=storage,
        placeholder_contract=discover_native_placeholder_contract(data),
    )
    await NativeTemplateVersionService.activate_version(
        db,
        tenant_scope=SCOPE,
        legal_entity_id=issuer.id,
        template_id=template.id,
        version_id=version.id,
    )
    parts = (
        [
            component("Внутренний блок", "2465.00", country="Малайзия"),
            component("Наружный блок", "4935.00"),
        ]
        if kind == "tn2"
        else None
    )
    selection = document_selection(
        kind, order, issuer, selected, source.source_revision, product, parts
    )
    if not parts:
        selection.waybill_composition.lines[0].whole_country = "Беларусь"
        selection = replace(
            selection,
            transport_terms=TransportTerms(
                loading_point="Склад", unloading_point="Объект"
            ),
        )
    draft = await ManagedDocumentService.create_draft(
        db, tenant_scope=SCOPE, selection=selection, template_storage=storage
    )
    assert draft.render_snapshot["meta"][
        "waybill_composition"
    ] == selection.waybill_composition.model_dump(mode="json")
    if kind == "ttn1":
        details = await ManagedDocumentDraftMutationService.get(
            db, tenant_scope=SCOPE, document_id=draft.id
        )
        assert details["waybill_cargo"][0]["quantity"] == "2"
        await ManagedDocumentDraftMutationService.update(
            db,
            tenant_scope=SCOPE,
            document_id=draft.id,
            expected_revision=details["revision"],
            changes={
                "waybill_cargo": [{"line_number": 1, "seats": 3, "mass_kg": "42.25"}]
            },
        )
        assert draft.render_snapshot["meta"][
            "waybill_composition"
        ] == selection.waybill_composition.model_dump(mode="json")
        values = draft.render_snapshot["values"]
        assert (
            values["transport.loading_point"] == "Склад"
            and values["totals.seats"] == "3"
        )
    assert product.logistics_components is None
    product.price = 9300
    await db.commit()
    result = await ManagedDocumentService.issue(
        db,
        tenant_scope=SCOPE,
        document_id=draft.id,
        template_storage=storage,
        artifact_storage=artifacts,
        pdf_converter=FakePdfConverter(),
    )
    artifact = next(item for item in result.artifacts if item.kind == "rendered_docx")
    recorded = Document(BytesIO(await private.read(artifact.storage_key)))
    rows = [[c.text for c in row.cells] for row in recorded.tables[0].rows[1:]]
    assert rows == (
        [
            ["Внутренний блок", "1", "2465.00", "2465.00", "Малайзия"],
            ["Наружный блок", "1", "4935.00", "4935.00", ""],
        ]
        if parts
        else [["Система Atlas", "2", "2470.00", "4940.00", "Беларусь"]]
    )
    assert any(
        ("Итого 7400.00" if parts else "Итого 4940.00") in p.text
        for p in recorded.paragraphs
    )
    with pytest.raises(DocumentContextError, match="изменились"):
        await DocumentContextBuilder.build(db, tenant_scope=SCOPE, selection=selection)


@pytest.mark.asyncio
async def test_waybill_rejects_stale_foreign_duplicate_missing_and_unbalanced_choices(
    db,
):
    order, issuer, selected, other, product = await seeded_waybill(db)
    product.quantity = 2
    product.logistics_components = [
        {"title": "Старая цена", "quantity_per_parent": 1, "unit_price": 7350}
    ]
    await db.commit()
    source = await DocumentContextBuilder.waybill_source(
        db, tenant_scope=SCOPE, order_id=order.id, proposal_id=selected.id
    )
    assert source.lines[0].components[0].unit_price == "7350.00"

    async def build(selection):
        return await DocumentContextBuilder.build(
            db, tenant_scope=SCOPE, selection=selection
        )

    selection = document_selection(
        "tn2",
        order,
        issuer,
        selected,
        source.source_revision,
        product,
        [component("Материалы", "1.01", 3), component("Система", "7396.97")],
    )
    snapshot = await build(selection)
    assert snapshot["values"]["totals.amount"] == "14800.00"
    assert snapshot["table_rows"]["lines"][0]["line.amount"] == "6.06"
    with pytest.raises(DocumentContextError, match="Проверьте цены"):
        await build(replace(selection, waybill_composition=None))
    with pytest.raises(DocumentContextError, match="Проверьте цены"):
        await build(
            document_selection(
                "tn2",
                order,
                issuer,
                selected,
                source.source_revision,
                product,
                [component("Система", "7399.99")],
            )
        )
    foreign = await db.scalar(
        select(OrderProductLink).where(OrderProductLink.proposal_id == other.id)
    )
    invalid = document_selection(
        "tn2", order, issuer, selected, source.source_revision, foreign, None
    )
    with pytest.raises(DocumentContextError, match="каждую товарную"):
        await build(invalid)
    picked = selection.waybill_composition.lines[0]
    duplicate = WaybillComposition(
        source_revision=source.source_revision, lines=[picked, picked]
    )
    with pytest.raises(DocumentContextError, match="каждую товарную"):
        await build(replace(selection, waybill_composition=duplicate))
    with pytest.raises(DocumentContextError, match="только для ТН-2"):
        await build(replace(selection, document_type="offer"))


@pytest.mark.asyncio
async def test_waybill_prints_only_known_countries(db):
    order, issuer, selected, _, link = await seeded_waybill(db)
    catalog = await db.get(Product, link.product_id)

    async def snapshot():
        return await DocumentContextBuilder.build(
            db,
            tenant_scope=SCOPE,
            selection=DocumentContextSelection(
                order_id=order.id,
                document_type="tn2",
                legal_entity_id=issuer.id,
                issue_date=date(2026, 11, 6),
                proposal_id=selected.id,
            ),
        )

    catalog.specs = {}
    await db.commit()
    assert (await snapshot())["table_rows"]["lines"][0]["line.country"] == ""
    catalog.specs = {"country": "Польша"}
    await db.commit()
    assert (await snapshot())["table_rows"]["lines"][0]["line.country"] == "Польша"
    link.logistics_components = [
        {
            "title": "Блок",
            "quantity_per_parent": 1,
            "unit_price": 7400,
            "country": "Малайзия",
        }
    ]
    await db.commit()
    assert (await snapshot())["table_rows"]["lines"][0]["line.country"] == "Малайзия"
