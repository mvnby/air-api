import pytest
from sqlalchemy import func
from sqlmodel import select

from core.security import create_access_token
from core.tenant_scope import get_public_tenant_scope
from models import GlobalConfig, StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from models.storefront_settings import StorefrontSettings
from models.tenancy import TenantScope
from schemas_storefront_settings import StorefrontSettingsPayload
from services.storefront_settings_service import StorefrontSettingsService


async def _partner(db, slug, role="owner"):
    tenant = Tenant(slug=slug, display_name=slug, is_system=False)
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


@pytest.mark.asyncio
async def test_partner_settings_are_owned_scoped_versioned_and_audited(async_client, db):
    scope_a, headers_a = await _partner(db, "settings-a")
    scope_b, headers_b = await _partner(db, "settings-b")
    db.add(GlobalConfig(key="email", value="platform@example.com"))
    db.add(GlobalConfig(key="private_setting", value="not-public"))
    await db.flush()

    first = await async_client.get("/api/manager/storefront-settings", headers=headers_a)
    assert first.status_code == 200
    state = first.json()
    assert state["version"] == 0
    assert state["site"]["email"] == ""
    assert all(not item["enabled"] for item in state["services"])
    state.pop("updated_at")
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
    unchanged = saved.json()
    unchanged.pop("updated_at")
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
async def test_public_projection_contains_only_selected_storefront_settings(async_client, db):
    from main import app

    scope, _ = await _partner(db, "public-settings")
    original = await StorefrontSettingsService.get_settings(db, tenant_scope=scope)
    payload = StorefrontSettingsPayload.model_validate(original.model_dump(exclude={"updated_at"}))
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
        current.model_dump(exclude={"updated_at"})
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
