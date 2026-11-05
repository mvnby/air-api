from importlib import import_module
from datetime import date
from io import BytesIO

import pytest
from docx import Document

from models import OrderDocument
from tests.integration import test_manager_document_system_api as api
from tests.integration.test_manager_document_system_api import (
    BASE,
    _local_document_storage,
)  # noqa: F401


def _transport_template():
    doc = Document()
    doc.add_paragraph("ТТН-1 № {{ document.official_full_number }}")
    doc.add_paragraph("Путевой лист: {{ transport.trip_sheet_number }}")
    doc.add_paragraph("Плательщик: {{ transport.freight_payer }}")
    doc.add_paragraph("Погрузка: {{ transport.loading_point }}")
    doc.add_paragraph("Разгрузка: {{ transport.unloading_point }}")
    for stage in ("loading", "unloading"):
        row = doc.add_table(rows=1, cols=5).rows[0]
        for cell, key in zip(
            row.cells,
            ("performer", "method", "arrived_at", "departed_at", "downtime"),
            strict=True,
        ):
            cell.text = "{{ transport." + stage + "." + key + " }}"
    stream = BytesIO()
    doc.save(stream)
    return stream.getvalue()


@pytest.mark.asyncio
async def test_manager_ttn_route_preview_edit_and_issue(async_client, db, monkeypatch):
    monkeypatch.setattr(api, "_template_docx", _transport_template)
    captured = []

    class CapturePdf(api._FakePdfConverter):
        def convert_docx(self, content, *, filename="document.docx"):
            captured.append(Document(BytesIO(content)))
            return super().convert_docx(content, filename=filename)

    monkeypatch.setattr(
        import_module("modules.documents.api.router"),
        "_pdf_converter",
        lambda: CapturePdf(),
    )
    headers = await api._legacy_owner_headers(async_client)
    issuer = await api._create_issuer(async_client, headers, name="Перевозчик")
    template, _ = await api._create_native_template(
        async_client, headers, legal_entity_id=issuer, document_type="ttn1"
    )
    order = await api._seed_order(db)
    basis = OrderDocument(
        order_id=order.id,
        tenant_id=1,
        legal_entity_id=issuer,
        doc_type="contract",
        status="issued",
        internal_reference="doc_ttn_basis",
        number="Д-001",
        official_number="001",
        official_date=date(2026, 5, 1),
        official_series="Д-",
        official_period_key="2026",
    )
    db.add(basis)
    await db.commit()
    selection = dict(
        legal_entity_id=issuer,
        document_type="ttn1",
        template_id=template,
        issue_date="2026-11-06",
        base_document_id=basis.id,
    )
    terms = dict(
        car_number="1234 АА-1",
        trip_sheet_number="б/н",
        freight_payer="Грузоотправитель",
        loading_point="Учебный склад 1",
        unloading_point="Учебный склад 2",
        loading={
            "performer": "Отправитель",
            "method": "ручной",
            "arrived_at": "2026-11-05T23:55",
            "departed_at": "2026-11-06T00:25",
            "downtime_minutes": 30,
        },
    )
    create_url = f"{BASE}/orders/{order.id}/documents/drafts"
    created = await async_client.post(
        create_url, headers=headers, json={**selection, "transport_terms": terms}
    )
    assert created.status_code == 200, created.text
    doc = f"{BASE}/documents/{created.json()['id']}"
    preview = await async_client.get(f"{doc}/preview", headers=headers)
    assert preview.status_code == 200, preview.text
    assert [c.text for c in captured[-1].tables[0].rows[0].cells] == [
        "Отправитель",
        "ручной",
        "05.11.2026 23:55",
        "06.11.2026 00:25",
        "0:30",
    ]
    assert [c.text for c in captured[-1].tables[1].rows[0].cells] == [""] * 5
    parameters_url = f"{doc}/draft/parameters"

    async def edit(change):
        revision = (await async_client.get(parameters_url, headers=headers)).json()[
            "revision"
        ]
        return await async_client.patch(
            parameters_url,
            headers=headers,
            json={"expected_revision": revision, "transport_terms": change},
        )

    # Clients that only know the existing car fields must not clear the route.
    assert (await edit({"driver_name": "Учебный водитель"})).status_code == 200
    after = (await async_client.get(parameters_url, headers=headers)).json()[
        "transport_terms"
    ]
    assert after["loading"] == terms["loading"] and after["trip_sheet_number"] == "б/н"
    assert (
        await edit(
            {
                "unloading": {
                    "arrived_at": "2026-11-06T10:00",
                    "departed_at": "2026-11-06T09:00",
                }
            }
        )
    ).status_code == 422
    assert (
        await edit({"unloading": {"arrived_at": "2026-02-31T10:00"}})
    ).status_code == 422
    update = await edit(
        {
            "unloading_point": "Учебный склад 3",
            "freight_payer": None,
            "unloading": {"performer": "Получатель", "downtime_minutes": 0},
        }
    )
    assert update.status_code == 200, update.text
    issued = await async_client.post(f"{doc}/issue", headers=headers)
    assert issued.status_code == 200, issued.text
    asset = next(a for a in issued.json()["artifacts"] if a["kind"] == "rendered_docx")
    download = await async_client.get(
        f"{BASE}/artifacts/{asset['id']}/download", headers=headers
    )
    assert download.status_code == 200
    saved = Document(BytesIO(download.content))
    text = [p.text.strip() for p in saved.paragraphs]
    assert "Погрузка: Учебный склад 1" in text and "Разгрузка: Учебный склад 3" in text
    assert "Плательщик:" in text and "Путевой лист: б/н" in text
    assert [c.text for c in saved.tables[1].rows[0].cells] == [
        "Получатель",
        "",
        "",
        "",
        "0:00",
    ]
    assert (await async_client.get(parameters_url, headers=headers)).status_code == 409
    without_transport = await async_client.post(create_url, headers=headers, json=selection)
    assert without_transport.status_code == 200, without_transport.text
    tn2, _ = await api._create_native_template(
        async_client, headers, legal_entity_id=issuer, document_type="tn2"
    )
    tn_selection = {**selection, "template_id": tn2, "document_type": "tn2"}
    goods_only = await async_client.post(create_url, headers=headers, json=tn_selection)
    assert goods_only.status_code == 200, goods_only.text
    bad = await async_client.post(
        create_url,
        headers=headers,
        json={
            **tn_selection,
            "transport_terms": {"loading_point": "Учебный склад"},
        },
    )
    assert bad.status_code == 400 and "только для ТТН-1" in bad.text, bad.text
