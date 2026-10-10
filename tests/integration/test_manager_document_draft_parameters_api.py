import pytest

from tests.integration.test_manager_document_system_api import (
    BASE,
    _create_issuer,
    _create_native_template,
    _legacy_owner_headers,
    _local_document_storage,
    _seed_order,
)


@pytest.mark.asyncio
async def test_draft_parameter_api_updates_existing_draft_and_rejects_stale_or_wrong_terms(
    async_client, db
):
    headers = await _legacy_owner_headers(async_client)
    issuer_id = await _create_issuer(async_client, headers, name="ООО Параметры")
    template_id, _ = await _create_native_template(
        async_client, headers, legal_entity_id=issuer_id
    )
    order = await _seed_order(db)
    created = await async_client.post(
        f"{BASE}/orders/{order.id}/documents/drafts",
        headers=headers,
        json={
            "legal_entity_id": issuer_id,
            "document_type": "contract",
            "issue_date": "2026-10-09",
            "template_id": template_id,
            "business_terms": {
                "contract_scenario": "services",
                "payment_schedule": [
                    {"share_percent": 100, "due_event": "before_work"}
                ],
            },
        },
    )
    assert created.status_code == 200, created.text
    document_id = created.json()["id"]
    url = f"{BASE}/documents/{document_id}/draft/parameters"
    parameters = await async_client.get(url, headers=headers)
    assert parameters.status_code == 200, parameters.text
    body = parameters.json()
    assert body["issue_date"] == "2026-10-09"
    assert body["business_terms"]["contract_scenario"] == "services"
    assert not body["has_editable_copy"]
    changed = await async_client.patch(
        url,
        headers=headers,
        json={"expected_revision": body["revision"], "issue_date": "2026-10-01"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["id"] == document_id
    assert changed.json()["date"].startswith("2026-10-01")
    assert changed.json()["official_number"] is None
    stale = await async_client.patch(
        url,
        headers=headers,
        json={"expected_revision": body["revision"], "issue_date": "2026-10-02"},
    )
    assert stale.status_code == 409, stale.text
    current = (await async_client.get(url, headers=headers)).json()
    incompatible = await async_client.patch(
        url,
        headers=headers,
        json={
            "expected_revision": current["revision"],
            "consumer_terms": {"equipment_model": "Не B2C"},
        },
    )
    assert incompatible.status_code == 400, incompatible.text
    null_date = await async_client.patch(
        url,
        headers=headers,
        json={"expected_revision": current["revision"], "issue_date": None},
    )
    assert null_date.status_code == 422
    listed = (
        await async_client.get(f"{BASE}/orders/{order.id}/documents", headers=headers)
    ).json()
    assert len(listed["items"]) == 1
    assert listed["items"][0]["date"].startswith("2026-10-01")
