"""Check the frozen factual scope against both real native Word templates."""

from datetime import datetime, timezone
from io import BytesIO

from docx import Document
from pydantic import ValidationError
import pytest

from modules.documents.application.native_template_discovery import discover_native_placeholder_contract
from modules.documents.application.order_technical_act_snapshot import OrderTechnicalActScope, extend_technical_act_snapshot
from modules.documents.infrastructure.renderers import DocumentTemplateVersion, NativeDocxRenderer, RenderContext
from modules.documents.infrastructure.renderers.order_technical_act_template import FIELDS, ROW_FIELDS, template_bytes
from schemas import ManagerEquipmentComponentItemResponse, ManagerEquipmentDetailResponse
from schemas_order_diagnostics import OrderInspectionFacts, OrderInspectionRevisionItem, PrepareOrderTechnicalActInput
from schemas_order_sites import OrderSiteItem, OrderSiteEquipmentItem


NOW = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)


@pytest.mark.parametrize("document_type", ["technical_inspection_act", "defect_act"])
def test_technical_docx_uses_frozen_equipment_and_distinct_observation_fields(document_type):
    site = OrderSiteItem(id=10, order_id=1, customer_branch_id=12, title="Тестовый объект", address="Тестовый адрес",
                         version=3, manager_url="https://example.test/orders/1")
    unit = ManagerEquipmentDetailResponse(
        id=20, customer_id=1, customer_branch_id=12, display_name="Тестовая установка",
        created_at=NOW, customer_phone="Private equipment contact", components=[
            ManagerEquipmentComponentItemResponse(id=25, equipment_id=20, component_type="drain_pump",
                                                  title="Дренажный насос", created_at=NOW),
            ManagerEquipmentComponentItemResponse(id=26, equipment_id=20, component_type="outdoor_unit",
                                                  model="ARCHIVED", is_archived=True, created_at=NOW),
        ],
    )
    other_unit = unit.model_copy(update={"id": 21, "display_name": "Вторая установка", "components": []})
    linked = (
        OrderSiteEquipmentItem(equipment_id=20, site_id=10, role="diagnostic", equipment=unit),
        OrderSiteEquipmentItem(equipment_id=21, site_id=10, role="diagnostic", equipment=other_unit),
    )
    inspections = {
        20: OrderInspectionRevisionItem(
            revision_id=30, version=1, status="restored", facts="Слив восстановлен",
            performed_actions="Дренаж очищен", recorded_at=NOW, recorded_by="test",
        ),
        21: OrderInspectionRevisionItem(
            revision_id=31, version=2, status="defect_found", facts="Недостаток хладагента",
            recommendations="Согласовать поиск утечки", recorded_at=NOW, recorded_by="test",
        ),
    }
    scope = OrderTechnicalActScope(site, linked, inspections, prepared_by_staff_id=40, prepared_by="test")
    values = {
        **dict.fromkeys(FIELDS, "Факт"),
        "order.object_title": site.title, "order.object_address": site.address, "totals.amount": "123.00",
    }
    snapshot = extend_technical_act_snapshot(
        {"values": values, "meta": {}, "conditions": {}, "table_rows": {"lines": [{"line.price": "123.00"}]}},
        scope,
    )
    assert scope.identifiers() == {"site_id": 10, "site_ids": [10], "equipment_ids": [20, 21]}
    assert snapshot["meta"]["order_technical_act"]["sources"][1]["inspection"]["version"] == 2
    assert "totals.amount" not in snapshot["values"] and "lines" not in snapshot["table_rows"]
    assert "Private equipment contact" not in str(snapshot) and "ARCHIVED" not in str(snapshot)

    content = template_bytes(document_type)
    contract = discover_native_placeholder_contract(content)
    assert contract.field_catalog == FIELDS
    assert contract.table_blocks[0].name == "inspections" and contract.table_blocks[0].row_fields == ROW_FIELDS
    template = DocumentTemplateVersion(
        template_key=document_type, version=1, source=content, field_catalog=contract.field_catalog,
        table_blocks=contract.table_blocks,
    )
    rendered = NativeDocxRenderer().render(
        template, RenderContext(values=snapshot["values"], table_rows=snapshot["table_rows"]),
    )
    document = Document(BytesIO(rendered.content))
    rows = [row.cells[0].text for row in document.tables[0].rows]
    assert len(rows) == 2
    assert "Дренажный насос" in rows[0] and "Дренаж очищен" in rows[0]
    assert "Согласовать поиск утечки" in rows[1] and "Фактически выполненные действия: —" in rows[1]
    assert "123.00" not in "\n".join(rows)


def test_written_actions_and_explicit_basis_are_validated():
    with pytest.raises(ValidationError, match="выполненные действия"):
        OrderInspectionFacts(status="restored", facts="Восстановлен")
    command = dict(order_id=1, site_id=2, expected_site_version=1, document_type="defect_act",
                   idempotency_key="technical-act-12345", issue_date="2026-11-20", legal_entity_id=3,
                   inspections=[{"equipment_id": 4, "expected_version": 1}])
    for basis in ({}, {"base_document_id": 5, "base_customer_contract_id": 6}):
        with pytest.raises(ValidationError, match="одно основание"):
            PrepareOrderTechnicalActInput(**command, **basis)
