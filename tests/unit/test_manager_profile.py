import io
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image, PngImagePlugin
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from api_contracts.manager_profile import ManagerOwnProfileUpdate
from core.database import get_session
from core.security import AuthenticatedUser, require_workspace_access
from models import LegacyOwnerAuthState, StaffAvatar, StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from routers.manager_profile import router
from services.staff_avatar_service import StaffAvatarError, sanitize_staff_avatar
from services.staff_user_service import StaffUserService


def png_bytes():
    image = Image.new("RGB", (640, 320), "red")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "private source metadata")
    output = io.BytesIO()
    image.save(output, "PNG", pnginfo=metadata)
    return output.getvalue()


def test_avatar_strips_metadata_and_has_bounded_dimensions():
    content, version = sanitize_staff_avatar(png_bytes())
    with Image.open(io.BytesIO(content)) as image:
        assert image.format == "WEBP"
        assert image.size == (256, 256)
        assert not image.info.get("exif") and "Comment" not in image.info
    assert len(content) <= 128 * 1024
    assert len(version) == 64


@pytest.mark.parametrize("content", [b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"invalid", b"", b"x" * (5 * 1024 * 1024 + 1)])
def test_avatar_rejects_unsupported_corrupt_or_oversized_input(content):
    with pytest.raises(StaffAvatarError):
        sanitize_staff_avatar(content)


def test_avatar_rejects_animation_and_excess_pixels(monkeypatch):
    output = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(
        output, "PNG", save_all=True, append_images=[Image.new("RGB", (10, 10), "blue")], duration=100,
    )
    with pytest.raises(StaffAvatarError, match="неподвижную"):
        sanitize_staff_avatar(output.getvalue())
    monkeypatch.setattr("services.staff_avatar_service.MAX_AVATAR_PIXELS", 100)
    with pytest.raises(StaffAvatarError, match="велико"):
        sanitize_staff_avatar(png_bytes())


@pytest.mark.parametrize("field,value", [("roles", ["owner"]), ("username", "takeover"),
                                        ("telegram_id", 99), ("display_name", None),
                                        ("telegram_notifications_enabled", None)])
def test_profile_dto_rejects_privilege_and_factor_changes(field, value):
    with pytest.raises(ValidationError):
        ManagerOwnProfileUpdate(expected_updated_at=datetime.now(timezone.utc), **{field: value})


@pytest.fixture
async def profile_context(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'profiles.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            Tenant(id=1, slug="mvn", display_name="MVN", is_system=True),
            Tenant(id=2, slug="partner", display_name="Partner"),
            Storefront(id=1, tenant_id=1, slug="main", display_name="MVN", status="active", is_default=True),
            Storefront(id=2, tenant_id=2, slug="main", display_name="Partner", status="active", is_default=True),
            StaffUser(id=10, display_name="Manager", username="manager", roles=["manager"], primary_role="manager", auth_version=2),
            StaffUser(id=11, display_name="Other", roles=["manager"], primary_role="manager"),
        ])
        await session.flush()
        session.add_all([
            LegacyOwnerAuthState(),
            TenantMembership(tenant_id=1, staff_user_id=10, role="manager"),
            TenantMembership(tenant_id=2, staff_user_id=11, role="manager"),
        ])
        await session.commit()
        context = {"auth": AuthenticatedUser(
            username="manager", auth_source="staff", staff_user_id=10, role="manager",
            tenant_id=1, storefront_id=1, auth_version=2, is_system_tenant=True,
        )}
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[require_workspace_access] = lambda: context["auth"]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield context, session, client
    await engine.dispose()


@pytest.mark.asyncio
async def test_profile_update_optimistic_atomic_and_self_only(profile_context):
    _, session, client = profile_context
    response = await client.get("/api/manager/account/profile")
    original = response.json()
    headers = {"X-Kitlane-Profile": "1"}
    result = await client.patch("/api/manager/account/profile", headers=headers, json={
        "expected_updated_at": original["updated_at"], "display_name": " Новое имя ",
        "email": " person@example.com ", "telegram_notifications_enabled": False,
    })
    assert result.status_code == 200, result.text
    assert result.json()["display_name"] == "Новое имя"
    assert result.json()["email"] == "person@example.com"
    assert result.json()["username"] == "manager"
    assert result.json()["telegram_notifications_enabled"] is False
    assert "password_hash" not in result.json()
    user = await session.get(StaffUser, 10)
    assert user.auth_version == 2 and user.primary_role == "manager"
    assert (await session.get(StaffUser, 11)).display_name == "Other"
    audit = (await session.execute(select(TenantAuditEvent))).scalar_one()
    assert audit.action == "staff_profile.updated" and audit.actor_staff_user_id == 10
    assert set(audit.change_set) == {"display_name", "email", "telegram_notifications_enabled"}
    stale = await client.patch("/api/manager/account/profile", headers=headers, json={
        "expected_updated_at": original["updated_at"], "display_name": "Overwrite",
    })
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "profile_changed"


@pytest.mark.asyncio
async def test_profile_writes_reject_cross_origin_and_revoked_sessions(profile_context):
    context, session, client = profile_context
    original = (await client.get("/api/manager/account/profile")).json()
    payload = {"expected_updated_at": original["updated_at"], "display_name": "Overwrite"}
    for headers in ({}, {"X-Kitlane-Profile": "1", "Origin": "https://hostile.example"}):
        result = await client.patch("/api/manager/account/profile", headers=headers, json=payload)
        assert result.status_code == 403
    context["auth"] = replace(context["auth"], auth_version=1)
    result = await client.patch("/api/manager/account/profile", headers={"X-Kitlane-Profile": "1"}, json=payload)
    assert result.status_code == 401
    assert (await session.get(StaffUser, 10)).display_name == "Manager"


@pytest.mark.asyncio
async def test_private_avatar_acl_precedes_etag_and_historical_member_allowed(profile_context):
    context, session, client = profile_context
    original_auth = context["auth"]
    profile = (await client.get("/api/manager/account/profile")).json()
    result = await client.post("/api/manager/account/profile/avatar", headers={"X-Kitlane-Profile": "1"},
                               data={"expected_updated_at": profile["updated_at"]},
                               files={"file": ("photo.png", png_bytes(), "image/png")})
    assert result.status_code == 200, result.text
    avatar_profile = result.json()
    url = avatar_profile["avatar_url"]
    assert url.startswith("/api/manager/staff/10/avatar?v=")
    photo = await client.get(url)
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/webp"
    assert photo.headers["cache-control"] == "private, no-cache"
    etag = photo.headers["etag"]
    assert (await client.get(url, headers={"If-None-Match": etag})).status_code == 304
    context["auth"] = replace(original_auth, staff_user_id=11, tenant_id=2, storefront_id=2)
    assert (await client.get(url, headers={"If-None-Match": etag})).status_code == 404
    context["auth"] = replace(context["auth"], is_platform_owner=True)
    assert (await client.get(url)).status_code == 200
    context["auth"] = original_auth
    member = await session.scalar(select(TenantMembership).where(TenantMembership.staff_user_id == 10))
    member.status = "disabled"
    session.add(member)
    await session.commit()
    assert (await client.get(url)).status_code == 200  # Historical order photos remain available.
    member.status = "active"
    session.add(member)
    await session.commit()
    removed = await client.request("DELETE", "/api/manager/account/profile/avatar",
                                   headers={"X-Kitlane-Profile": "1"},
                                   json={"expected_updated_at": avatar_profile["updated_at"]})
    assert removed.status_code == 200 and removed.json()["avatar_url"] is None
    assert await session.get(StaffAvatar, 10) is None
    assert (await client.get(url, headers={"If-None-Match": etag})).status_code == 404


@pytest.mark.asyncio
async def test_merged_identity_never_authenticates_or_mutates(profile_context):
    context, session, client = profile_context
    user = await session.get(StaffUser, 10)
    user.merged_into_staff_user_id = 11
    session.add(user)
    await session.commit()
    assert not StaffUserService.is_active(user)
    assert (await client.get("/api/manager/account/profile")).status_code == 409
    directory = await StaffUserService.list_staff(session, tenant_scope=context["auth"].tenant_scope())
    assert directory.items == []
