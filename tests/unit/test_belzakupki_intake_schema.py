"""Pure validation of the bounded native opportunity boundary."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from schemas_belzakupki_intake import NativeOpportunity
from services.belzakupki_import_service import BelzakupkiImportService


def native_item():
    return {"id": 11, "profile": {"id": 7, "name": "HVAC"}, "score": 0.91,
            "relevance_status": "confirmed", "eligible": True, "reason": "HVAC relevance",
            "updated_at": "2026-10-09T10:00:00+00:00",
            "tender": {"source": "native-source", "external_id": "tender-42", "title": "Native tender",
                       "url": "https://example.test/tender/42", "deadline_at": "2099-10-01T10:00:00+00:00"}}


@pytest.mark.parametrize("path,value", [
    (("id",), True), (("id",), "11"), (("id",), 0), (("profile", "id"), False),
    (("eligible",), "true"), (("updated_at",), "2026-10-09T10:00:00"),
    (("tender", "deadline_at"), "bad"), (("tender", "published_at"), "2026-10-09"),
    (("tender", "source"), " "), (("tender", "external_id"), ""),
    (("tender", "url"), "https://user:password@example.test/a"),
    (("tender", "url"), "javascript:alert(1)"), (("tender", "url"), "https://example.test:bad/a"),
    (("tender", "url"), "https://example.test/a\nb"), (("reason",), "a" * 4001),
    (("tenant_id",), 999), (("tender", "role_id"), 1), (("score",), float("nan")),
])
def test_invalid_native_payload_rejected(path, value):
    item = native_item()
    target = item
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        NativeOpportunity.model_validate(item)


def test_evidence_bounded_in_utf8_and_preserved():
    item = native_item()
    item["ai_analysis"] = {"explanation": "Native source reason"}
    assert NativeOpportunity.model_validate(item).ai_analysis == item["ai_analysis"]
    item["ai_analysis"] = {"explanation": "я" * 33000}
    with pytest.raises(ValidationError, match="64 KiB"):
        NativeOpportunity.model_validate(item)


def test_older_profile_does_not_replace_newer_tender_snapshot():
    old = native_item()
    fresh = deepcopy(old)
    fresh["updated_at"] = "2026-10-09T11:00:00+00:00"
    fresh["tender"]["title"] = "Fresh tender"
    snapshot = BelzakupkiImportService._match_snapshot(fresh)
    metadata = BelzakupkiImportService._next_metadata(existing={}, snapshot=snapshot, snapshot_fingerprint="fresh")
    old["id"] = 12
    snapshot = BelzakupkiImportService._match_snapshot(old)
    updated = BelzakupkiImportService._next_metadata(existing=metadata, snapshot=snapshot, snapshot_fingerprint="old")
    assert updated["tender"]["title"] == "Fresh tender"
    assert set(updated["matches"]) == {"11", "12"}


def test_dedicated_key_excluded_from_settings_repr_and_serialization(monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "BELZAKUPKI_LEAD_PUSH_API_KEY", "dedicated-secret-for-test")
    assert "dedicated-secret-for-test" not in repr(settings)
    assert "BELZAKUPKI_LEAD_PUSH_API_KEY" not in settings.model_dump()


def test_pull_push_equivalent_timestamp_has_same_snapshot():
    original = native_item()
    pushed = NativeOpportunity.model_validate(original).model_dump(mode="json")
    assert BelzakupkiImportService._match_snapshot(original) == BelzakupkiImportService._match_snapshot(pushed)
