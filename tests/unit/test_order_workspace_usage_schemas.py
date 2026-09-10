import pytest
from pydantic import ValidationError

from schemas_order_usage import OrderUsageBatch


EVENT = dict(metric="product_add", workflow="maintenance", party_kind="company", viewport="desktop")


@pytest.mark.parametrize("field,value", [
    ("metric", "arbitrary DOM text"), ("workflow", "other"),
    ("party_kind", "Customer name"), ("viewport", "1920x1080"),
    ("order_id", 395), ("customer_id", 1), ("text", "private comment"),
    ("x", 300), ("count", 1000), ("timestamp", "2026-09-10"),
    ("tenant_id", 2), ("storefront_id", 2),
])
def test_usage_event_rejects_content_identifiers_and_unknown_dimensions(field, value):
    with pytest.raises(ValidationError):
        OrderUsageBatch.model_validate({"events": [{**EVENT, field: value}]})


@pytest.mark.parametrize("payload", [
    {"events": []}, {"events": [EVENT] * 26},
    {"events": [EVENT], "tenant_id": 2},
    {"events": [EVENT], "session_id": "anything"},
    {"events": [EVENT], "layout_version": "other"},
])
def test_usage_batch_has_bounded_finite_shape(payload):
    with pytest.raises(ValidationError):
        OrderUsageBatch.model_validate(payload)


def test_usage_batch_accepts_at_most_twenty_five_semantic_events():
    payload = OrderUsageBatch.model_validate({"events": [EVENT] * 25})
    assert len(payload.events) == 25
    assert payload.layout_version == "workspace_v1"
