import pytest

from core.config import settings
from models import InstallationPriceBook, InstallationRate
from models.tenancy import Tenant


async def _auth_headers(async_client):
    login_response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_manager_installation_rates_are_public_checkout_rates_not_service_tariffs(
    async_client, db
):
    cassette = InstallationRate(
        category="Cassette",
        power_range="All",
        base_price=1200,
        extra_pipe_price=85,
        included_pipe_meters=3,
        is_fixed=False,
        comment="survey",
    )
    db.add(cassette)
    await db.commit()
    await db.refresh(cassette)
    headers = await _auth_headers(async_client)

    listed = await async_client.get("/api/manager/installation-rates", headers=headers)

    assert listed.status_code == 200
    item = next(item for item in listed.json()["items"] if item["id"] == cassette.id)
    assert item["equipment_label"] == "Кассетный кондиционер"
    assert item["power_label"] == "Любая мощность"
    assert item["selection_status"] == "matched_manual_quote"
    assert item["title"] == "Монтаж кассетного кондиционера"

    updated = await async_client.put(
        f"/api/manager/installation-rates/{cassette.id}",
        headers=headers,
        json={
            "base_price": 1500,
            "extra_pipe_price": 90,
            "included_pipe_meters": 4,
            "comment": "confirmed",
        },
    )

    assert updated.status_code == 200
    assert updated.json()["base_price"] == 1500
    assert updated.json()["selection_status"] == "matched_manual_quote"
    await db.refresh(cassette)
    assert cassette.category == "Cassette"
    assert cassette.power_range == "All"
    assert cassette.is_fixed is False

    rejected = await async_client.put(
        f"/api/manager/installation-rates/{cassette.id}",
        headers=headers,
        json={
            "base_price": 1500,
            "extra_pipe_price": 90,
            "included_pipe_meters": 4,
            "category": "Wall",
        },
    )
    assert rejected.status_code == 422
    await db.refresh(cassette)
    assert cassette.category == "Cassette"

    null_price = await async_client.put(
        f"/api/manager/installation-rates/{cassette.id}",
        headers=headers,
        json={
            "base_price": None,
            "extra_pipe_price": 90,
            "included_pipe_meters": 4,
        },
    )
    assert null_price.status_code == 422


@pytest.mark.asyncio
async def test_manager_installation_rates_require_manager_auth(async_client):
    response = await async_client.get("/api/manager/installation-rates")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_publishing_book_retires_legacy_editor_and_rejects_stale_save(async_client, db):
    rate = InstallationRate(category="Wall", power_range="07-12", base_price=600,
                            extra_pipe_price=50, included_pipe_meters=3, is_fixed=True)
    db.add(rate)
    await db.commit()
    await db.refresh(rate)
    headers = await _auth_headers(async_client)
    before = await async_client.get("/api/manager/installation-rates", headers=headers)
    assert before.status_code == 200
    assert before.json()["published_price_book_revision"] is None
    assert any(item["id"] == rate.id for item in before.json()["items"])

    db.add(InstallationPriceBook(tenant_id=1, revision=1, fingerprint="editor-retired", entries=[]))
    await db.commit()
    after = await async_client.get("/api/manager/installation-rates", headers=headers)
    assert after.json() == {"items": [], "published_price_book_revision": 1}
    rejected = await async_client.put(
        f"/api/manager/installation-rates/{rate.id}", headers=headers,
        json={"base_price": 1, "extra_pipe_price": 1, "included_pipe_meters": 1},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "installation_rates_retired"
    await db.refresh(rate)
    assert (rate.base_price, rate.extra_pipe_price, rate.included_pipe_meters) == (600, 50, 3)


@pytest.mark.asyncio
async def test_other_tenants_book_does_not_retire_canonical_editor(async_client, db):
    partner = Tenant(slug="rate-editor-partner", display_name="Partner", is_system=False)
    db.add(partner)
    await db.flush()
    db.add(InstallationPriceBook(tenant_id=partner.id, revision=7, fingerprint="other-book", entries=[]))
    rate = InstallationRate(category="Wall", power_range="07-12", base_price=600,
                            extra_pipe_price=50, included_pipe_meters=3, is_fixed=True)
    db.add(rate)
    await db.commit()
    await db.refresh(rate)
    headers = await _auth_headers(async_client)
    listed = await async_client.get("/api/manager/installation-rates", headers=headers)
    assert listed.json()["published_price_book_revision"] is None
    saved = await async_client.put(
        f"/api/manager/installation-rates/{rate.id}", headers=headers,
        json={"base_price": 650, "extra_pipe_price": 55, "included_pipe_meters": 3},
    )
    assert saved.status_code == 200
    assert saved.json()["base_price"] == 650
