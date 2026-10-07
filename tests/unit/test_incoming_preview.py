import pytest
from pydantic import ValidationError
from schemas_incoming import IncomingCreatePayload, IncomingUpdatePayload
from services.incoming_preview import incoming_preview


@pytest.mark.parametrize("text,region,service", [
    ("ТО квартиры, +375291234567, район Билево, завтра 09:00; адрес уточнить", "Билево", "maintenance"),
    ("обслуживание, район Билево", "Билево", "maintenance"),
    ("ремонт кондиционера", None, "repair"),
    ("кондиционер не холодит", None, "repair"),
    ("купить кондиционер и установить", None, "turnkey"),
    ("ТО или ремонт, район Билево или Центр", None, None),
    ("возможно обслуживание; район неизвестен", None, None),
    ("не обслуживание, ремонт", None, None),
    ("район Билево; район Центр", None, None),
    ("район Билево завтра в 09:00", None, None),
    ("кондиционер в квартире", None, None),
    ("это квартира, потом уточним", None, None),
    ("если нужно, то позвоните", None, None),
    ("район Билево?", None, None),
    ("район Билево, возможно район Центр", None, None),
    ("район Билево; район Центр?", None, None),
    ("район Билево", "Билево", None),
    ("Обслуживание отменено", None, None),
    ("Отказались от ремонта кондиционера", None, None),
    ("Если понадобится ремонт, клиент перезвонит", None, None),
    ("Ранее выполнен ремонт кондиционера", None, None),
    ("Обслуживание уже завершено", None, None),
    ("Нужно обслуживание кондиционера", None, "maintenance"),
    ("Нужен ремонт кондиционера завтра", None, "repair"),
    ("Выполнить обслуживание кондиционера", None, "maintenance"),
    ("Завершить монтаж кондиционера", None, "install_only"),
    ("Ремонт кондиционера был вчера", None, None),
    ("Обслуживание проводили вчера", None, None),
    ("Отменили заявку. Обслуживание кондиционера", None, None),
])
def test_conservative_suggestions(text, region, service):
    preview = incoming_preview(text)
    assert preview.region_text == region and preview.service_type == service
    assert preview.state == ("suggested" if region or service else "unknown")
    assert all(source == "text" for source in preview.field_sources.values())
    assert all(fragment in text for fragment in preview.evidence.values())


@pytest.mark.parametrize("model,extra", [(IncomingCreatePayload, {}), (IncomingUpdatePayload, {"expected_version": 1})])
def test_incoming_rejects_inconsistent_or_unknown_scenarios(model, extra):
    for fields in [{"service_type": "fictional"}, {"workflow_type": "maintenance", "service_type": "repair"}]:
        with pytest.raises(ValidationError):
            model(request_text="Запрос", **extra, **fields)


def test_repeating_workflow_preserves_omitted_service_and_provenance():
    from services.incoming_command_service import IncomingCommandService
    meta = {"workflow_type": "service_work", "service_type": "dismantling",
            "field_sources": {"workflow_type": "text", "service_type": "text"}}
    updated = IncomingCommandService._updated_meta(
        IncomingUpdatePayload(request_text="Демонтаж", expected_version=1,
                              workflow_type="service_work"), meta, None)
    assert updated["service_type"] == "dismantling"
    assert updated["workflow_type"] == "service_work"
    assert updated["field_sources"] == meta["field_sources"]


@pytest.mark.parametrize("fields", [
    {"workflow_type": "repair"}, {"service_type": "repair"},
])
def test_partial_incompatible_scenario_is_rejected(fields):
    from services.incoming_command_service import IncomingCommandService
    meta = {"workflow_type": "service_work", "service_type": "dismantling"}
    with pytest.raises(ValueError, match="conflicts"):
        IncomingCommandService._updated_meta(
            IncomingUpdatePayload(request_text="Демонтаж", expected_version=1, **fields), meta, None)


@pytest.mark.parametrize("fields,expected", [
    ({"service_type": None}, ("service_work", None)),
    ({"workflow_type": None}, (None, None)),
    ({"workflow_type": None, "service_type": None}, (None, None)),
])
def test_explicit_scenario_clear_is_distinct_from_omission(fields, expected):
    from services.incoming_command_service import IncomingCommandService
    meta = {"workflow_type": "service_work", "service_type": "dismantling",
            "field_sources": {"workflow_type": "text", "service_type": "text"}}
    updated = IncomingCommandService._updated_meta(
        IncomingUpdatePayload(request_text="Демонтаж", expected_version=1, **fields), meta, None)
    assert (updated["workflow_type"], updated["service_type"]) == expected
    assert "service_type" not in updated["field_sources"]
    if expected[0] is None:
        assert "workflow_type" not in updated["field_sources"]


def test_explicit_clear_of_canonical_service_clears_omitted_workflow():
    from services.incoming_command_service import IncomingCommandService
    updated = IncomingCommandService._updated_meta(
        IncomingUpdatePayload(request_text="Ремонт", expected_version=1, service_type=None),
        {"workflow_type": "repair", "service_type": "repair",
         "field_sources": {"workflow_type": "text", "service_type": "text"}}, None)
    assert updated["workflow_type"] is None and updated["service_type"] is None
    assert updated["field_sources"] == {}


def test_explicit_workflow_cannot_restore_explicitly_cleared_canonical_service():
    from services.incoming_command_service import IncomingCommandService
    with pytest.raises(ValueError, match="conflicts"):
        IncomingCommandService._updated_meta(
            IncomingUpdatePayload(request_text="Ремонт", expected_version=1,
                                  workflow_type="repair", service_type=None),
            {"workflow_type": "repair", "service_type": "repair"}, None)
