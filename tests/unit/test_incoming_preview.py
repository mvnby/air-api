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
