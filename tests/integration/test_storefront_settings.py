import pytest
from sqlalchemy import func
from sqlmodel import select

from core.security import create_access_token
from core.tenant_scope import get_public_tenant_scope
from models import GlobalConfig, MediaAsset, StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from models.storefront_settings import StorefrontSettings
from models.tenancy import TenantScope
from schemas_storefront_settings import StorefrontSettingsPayload
from services.storefront_settings_service import StorefrontSettingsService
from services.media_library_service import MediaLibraryService, StoredLibraryImage


async def _partner(db, slug, role="owner", demo=False):
    tenant = Tenant(slug=slug, display_name=slug, is_system=False, demo_read_only=demo)
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug="main", display_name=slug, status="active", is_default=True)
    user = StaffUser(username=slug, display_name=slug, status="active", primary_role=role, roles=[role])
    db.add_all([storefront, user])
    await db.flush()
    db.add(TenantMembership(tenant_id=tenant.id, staff_user_id=user.id, role=role, status="active"))
    await db.flush()
    headers = {"Authorization": "Bearer " + create_access_token({"sub": user.username, "staff_user_id": user.id, "auth_version": user.auth_version, "auth_source": "storefront-settings-test"})}
    return TenantScope(tenant_id=tenant.id, storefront_id=storefront.id), headers


def _editable(response):
    state = response.json()
    state.pop("updated_at")
    state["site"].pop("logo_url")
    state["site"].pop("compact_logo_url")
    return state


@pytest.mark.asyncio
async def test_partner_settings_are_owned_scoped_versioned_and_audited(async_client, db):
    scope_a, headers_a = await _partner(db, "settings-a")
    scope_b, headers_b = await _partner(db, "settings-b")
    db.add(GlobalConfig(key="email", value="platform@example.com"))
    db.add(GlobalConfig(key="private_setting", value="not-public"))
    await db.flush()

    first = await async_client.get("/api/manager/storefront-settings", headers=headers_a)
    assert first.status_code == 200
    state = _editable(first)
    assert state["version"] == 0
    assert state["site"]["email"] == ""
    assert all(not item["enabled"] for item in state["services"])
    state["site"]["email"] = "owner-a@example.com"
    state["site"]["support_telegram_url"] = "@partner_help_bot"
    state["services"][0]["enabled"] = True

    invalid = await async_client.put("/api/manager/storefront-settings", headers=headers_a, json={**state, "tenant_id": scope_b.tenant_id})
    assert invalid.status_code == 422
    saved = await async_client.put("/api/manager/storefront-settings", headers=headers_a, json=state)
    assert saved.status_code == 200
    assert saved.json()["version"] == 1
    assert saved.json()["site"]["support_telegram_url"] == "https://t.me/partner_help_bot"
    other = await async_client.get("/api/manager/storefront-settings", headers=headers_b)
    assert other.json()["site"]["email"] == ""
    assert other.json()["version"] == 0

    stale = await async_client.put("/api/manager/storefront-settings", headers=headers_a, json=state)
    assert stale.status_code == 409
    unchanged = _editable(saved)
    repeated = await async_client.put("/api/manager/storefront-settings", headers=headers_a, json=unchanged)
    assert repeated.json()["version"] == 1
    assert (await db.execute(select(func.count()).select_from(TenantAuditEvent).where(TenantAuditEvent.tenant_id == scope_a.tenant_id))).scalar_one() == 1
    assert (await db.execute(select(func.count()).select_from(StorefrontSettings))).scalar_one() == 1


@pytest.mark.asyncio
async def test_manager_cannot_change_owner_settings(async_client, db):
    _, headers = await _partner(db, "settings-manager", role="manager")
    response = await async_client.get("/api/manager/storefront-settings", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_brand_assets_are_scoped_for_manager_and_public_reads(async_client, db):
    from main import app

    scope_a, owner_a = await _partner(db, "brand-a")
    scope_b, owner_b = await _partner(db, "brand-b")
    manager_user = StaffUser(username="brand-manager", display_name="Brand manager", status="active", primary_role="manager", roles=["manager"])
    db.add(manager_user)
    await db.flush()
    db.add(TenantMembership(tenant_id=scope_a.tenant_id, staff_user_id=manager_user.id, role="manager", status="active"))
    await db.flush()
    manager = {"Authorization": "Bearer " + create_access_token({"sub": manager_user.username, "staff_user_id": manager_user.id, "auth_version": manager_user.auth_version, "auth_source": "storefront-settings-test"})}
    logo = MediaAsset(tenant_id=scope_a.tenant_id, storefront_id=scope_a.storefront_id,
                      kind="storefront_logo", url="/media/library/original/brand-a.svg", processing_status="ready")
    foreign = MediaAsset(tenant_id=scope_b.tenant_id, storefront_id=scope_b.storefront_id,
                         kind="storefront_logo", url="/media/library/original/brand-b.svg", processing_status="ready")
    second_storefront = Storefront(tenant_id=scope_a.tenant_id, slug="secondary", display_name="Другой сайт", status="active", is_default=False)
    db.add(second_storefront)
    await db.flush()
    sibling = MediaAsset(tenant_id=scope_a.tenant_id, storefront_id=second_storefront.id,
                         kind="storefront_logo", url="/media/library/original/brand-a-secondary.svg", processing_status="ready")
    db.add_all([logo, foreign, sibling])
    await db.flush()

    state = _editable(await async_client.get("/api/manager/storefront-settings", headers=owner_a))
    state["site"]["logo_asset_id"] = foreign.id
    assert (await async_client.put("/api/manager/storefront-settings", headers=owner_a, json=state)).status_code == 422
    state["site"]["logo_asset_id"] = sibling.id
    assert (await async_client.put("/api/manager/storefront-settings", headers=owner_a, json=state)).status_code == 422
    state["site"]["logo_asset_id"] = logo.id
    state["site"]["display_name"] = "Бренд А"
    saved = await async_client.put("/api/manager/storefront-settings", headers=owner_a, json=state)
    assert saved.status_code == 200
    assert saved.json()["site"]["logo_url"] == logo.url
    with pytest.raises(ValueError, match="kind cannot be changed"):
        await MediaLibraryService.update_asset(db, asset_id=logo.id, kind="misc")
    await MediaLibraryService.update_asset(db, asset_id=logo.id, kind="storefront_logo", title="Обновлённое название")
    assert (await async_client.get("/api/manager/storefront-settings/brand", headers=owner_a)).json()["logo_url"] == logo.url
    with pytest.raises(ValueError, match="published storefront logo"):
        await MediaLibraryService.delete_asset(db, asset_id=logo.id, force=True)

    manager_brand = await async_client.get("/api/manager/storefront-settings/brand", headers=manager)
    assert manager_brand.status_code == 200
    assert manager_brand.json()["logo_url"] == logo.url
    sibling_brand = await async_client.get("/api/manager/storefront-settings/brand", headers={**manager, "X-MVN-Manager-Storefront": "secondary"})
    assert sibling_brand.status_code == 200
    assert sibling_brand.json() == {"display_name": "Другой сайт", "logo_url": None, "compact_logo_url": None}
    assert (await async_client.get("/api/manager/storefront-settings/brand", headers=owner_a)).json()["logo_url"] == logo.url
    assert (await async_client.get("/api/manager/storefront-settings/brand", headers=owner_b)).json()["logo_url"] is None
    assert (await async_client.get("/api/manager/storefront-settings", headers=manager)).status_code == 403

    app.dependency_overrides[get_public_tenant_scope] = lambda: scope_a
    assert (await async_client.get("/api/v1/storefront-settings")).json()["site"]["logo_url"] == logo.url
    app.dependency_overrides[get_public_tenant_scope] = lambda: scope_b
    assert (await async_client.get("/api/v1/storefront-settings")).json()["site"]["logo_url"] is None


@pytest.mark.asyncio
async def test_logo_upload_uses_scoped_media_pipeline_and_owner_access(async_client, db, monkeypatch):
    scope, owner = await _partner(db, "logo-upload")
    _, manager = await _partner(db, "logo-upload-manager", role="manager")

    async def stored(_content, *, variant_type):
        assert variant_type == "original"
        url = f"/media/library/original/{'a' * 64}.svg"
        return StoredLibraryImage(url=url, path=url.lstrip("/"),
                                  content_hash="a" * 64, width=100, height=50, size_bytes=20, mime_type="image/svg+xml")

    monkeypatch.setattr(MediaLibraryService, "_store_image", stored)
    file = {"file": ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")}
    assert (await async_client.post("/api/manager/storefront-settings/logo", headers=manager, files=file)).status_code == 403
    response = await async_client.post("/api/manager/storefront-settings/logo", headers=owner, files=file)
    assert response.status_code == 200
    asset = await db.get(MediaAsset, response.json()["items"][0]["id"])
    assert (asset.tenant_id, asset.storefront_id, asset.kind) == (scope.tenant_id, scope.storefront_id, "storefront_logo")


@pytest.mark.asyncio
async def test_demo_can_read_brand_but_cannot_upload_or_publish_logo(async_client, db):
    _, demo = await _partner(db, "logo-demo", demo=True)
    assert (await async_client.get("/api/manager/storefront-settings/brand", headers=demo)).status_code == 200
    assert (await async_client.get("/api/manager/storefront-settings", headers=demo)).status_code == 200
    file = {"file": ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")}
    upload = await async_client.post("/api/manager/storefront-settings/logo", headers=demo, files=file)
    assert upload.status_code == 403
    assert upload.json()["detail"]["code"] == "demo_read_only"
    payload = _editable(await async_client.get("/api/manager/storefront-settings", headers=demo))
    assert (await async_client.put("/api/manager/storefront-settings", headers=demo, json=payload)).status_code == 403


@pytest.mark.asyncio
async def test_public_projection_contains_only_selected_storefront_settings(async_client, db):
    from main import app

    scope, _ = await _partner(db, "public-settings")
    original = await StorefrontSettingsService.get_settings(db, tenant_scope=scope)
    payload = StorefrontSettingsPayload.model_validate(original.model_dump(exclude={"updated_at": True, "site": {"logo_url", "compact_logo_url"}}))
    payload.site.email = "public@example.com"
    payload.services[3].enabled = True
    await StorefrontSettingsService.update_settings(db, tenant_scope=scope, payload=payload, actor_username="public-settings", actor_staff_user_id=None)
    app.dependency_overrides[get_public_tenant_scope] = lambda: scope
    response = await async_client.get("/api/v1/storefront-settings")
    assert response.status_code == 200
    assert response.json()["site"]["email"] == "public@example.com"
    assert set(response.json()) == {"site", "services", "version", "updated_at"}
    assert await StorefrontSettingsService.is_service_enabled(db, tenant_scope=scope, service_kind="maintenance")
    assert not await StorefrontSettingsService.is_service_enabled(db, tenant_scope=scope, service_kind="repair")

    second = Storefront(tenant_id=scope.tenant_id, slug="second", display_name="Second", status="active", is_default=False)
    db.add(second)
    await db.flush()
    second_scope = TenantScope(tenant_id=scope.tenant_id, storefront_id=second.id)
    settings = await StorefrontSettingsService.get_settings(db, tenant_scope=second_scope)
    assert settings.site.email == ""
    assert all(not item.enabled for item in settings.services)


@pytest.mark.asyncio
async def test_canonical_public_config_uses_saved_storefront_contacts(async_client, db):
    from main import app

    tenant = (
        await db.execute(select(Tenant).where(Tenant.slug == "mvn"))
    ).scalar_one()
    storefront = (
        await db.execute(
            select(Storefront).where(
                Storefront.tenant_id == tenant.id,
                Storefront.is_default.is_(True),
            )
        )
    ).scalar_one()
    db.add_all(
        [
            GlobalConfig(key="phone", value="+375 29 100-00-00"),
            GlobalConfig(key="email", value="legacy@example.com"),
        ]
    )
    await db.flush()
    scope = TenantScope(
        tenant_id=tenant.id,
        storefront_id=storefront.id,
        is_system=True,
        is_canonical_storefront=True,
    )
    app.dependency_overrides[get_public_tenant_scope] = lambda: scope

    legacy = await async_client.get("/api/v1/config")
    assert legacy.status_code == 200
    assert legacy.json()["email"] == "legacy@example.com"

    current = await StorefrontSettingsService.get_settings(
        db,
        tenant_scope=scope,
    )
    payload = StorefrontSettingsPayload.model_validate(
        current.model_dump(exclude={"updated_at": True, "site": {"logo_url", "compact_logo_url"}})
    )
    payload.site.phone = "+375 29 222-33-44"
    payload.site.email = "saved@example.com"
    payload.site.address = "Минск, сохранённый адрес"
    payload.site.work_hours = "Пн–Пт 9:00–18:00"
    await StorefrontSettingsService.update_settings(
        db,
        tenant_scope=scope,
        payload=payload,
        actor_username="canonical-owner",
        actor_staff_user_id=None,
    )

    saved = await async_client.get("/api/v1/config")
    assert saved.status_code == 200
    assert saved.json()["phone"] == "+375 29 222-33-44"
    assert saved.json()["phone_clean"] == "375292223344"
    assert saved.json()["email"] == "saved@example.com"
    assert saved.json()["address"] == "Минск, сохранённый адрес"
    assert saved.json()["work_hours"] == "Пн–Пт 9:00–18:00"
