import pytest
from pydantic import ValidationError

from schemas_catalog_usage import CatalogUsageBatch


EVENT = dict(device="desktop", action="edit_gallery", outcome="success", duration_bucket="1_3s")


@pytest.mark.parametrize("field,value", [
    ("product_id", 10), ("staff_user_id", 2), ("tenant_id", 1), ("form", {"name": "private"}),
    ("title", "Product name"), ("duration_ms", 900), ("device", "1920x1080"),
])
def test_catalog_usage_event_rejects_identifiers_content_and_unbounded_dimensions(field, value):
    with pytest.raises(ValidationError):
        CatalogUsageBatch.model_validate({"events": [{**EVENT, field: value}]})


@pytest.mark.parametrize("payload", [
    {"events": []}, {"events": [EVENT] * 26}, {"events": [EVENT], "pilot_opt_in": False},
    {"events": [EVENT], "layout_version": "unknown"}, {"events": [EVENT], "account": "someone"},
])
def test_catalog_usage_batch_is_a_bounded_opted_in_pilot_contract(payload):
    with pytest.raises(ValidationError):
        CatalogUsageBatch.model_validate(payload)


def test_catalog_usage_batch_accepts_only_its_finite_aggregate_shape():
    payload = CatalogUsageBatch.model_validate({"events": [EVENT] * 25})
    assert payload.pilot_opt_in is True
    assert payload.layout_version == "catalog_workspace_v1"
