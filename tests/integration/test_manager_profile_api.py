"""Real PostgreSQL profile timestamps, private photo access and audit commit."""

import io

import pytest
from PIL import Image
from sqlmodel import select

from models import StaffAvatar, Storefront, Tenant, TenantAuditEvent
from models.tenancy import TenantScope
from schemas import ManagerStaffCreatePayload
from services.staff_user_service import StaffUserService


async def staff_token(client, db, *, username, scope):
    await StaffUserService.create_staff(
        db, ManagerStaffCreatePayload(
            display_name=username, primary_role="manager", username=username, password="profile-test-password",
        ), tenant_scope=scope,
    )
    response = await client.post("/login/access-token", data={"username": username, "password": "profile-test-password"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}", "X-Kitlane-Profile": "1"}


@pytest.mark.asyncio
async def test_profile_pg_timestamp_photo_and_cross_company_access(async_client, db):
    headers = await staff_token(async_client, db, username="profile-manager", scope=TenantScope(tenant_id=1, storefront_id=1))
    before = (await async_client.get("/api/manager/account/profile", headers=headers)).json()
    changed = await async_client.patch("/api/manager/account/profile", headers=headers, json={
        "expected_updated_at": before["updated_at"], "display_name": "Личный профиль", "phone": "+375291234567",
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["display_name"] == "Личный профиль"
    assert changed.json()["updated_at"] != before["updated_at"]
    stale = await async_client.patch("/api/manager/account/profile", headers=headers, json={
        "expected_updated_at": before["updated_at"], "display_name": "Перезапись",
    })
    assert stale.status_code == 409
    content = io.BytesIO()
    Image.new("RGB", (300, 200), "blue").save(content, "JPEG")
    uploaded = await async_client.post("/api/manager/account/profile/avatar", headers=headers,
                                       data={"expected_updated_at": changed.json()["updated_at"]},
                                       files={"file": ("photo.jpg", content.getvalue(), "image/jpeg")})
    assert uploaded.status_code == 200, uploaded.text
    url = uploaded.json()["avatar_url"]
    photo = await async_client.get(url, headers=headers)
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/webp"
    etag = photo.headers["etag"]
    assert (await async_client.get(url, headers={**headers, "If-None-Match": etag})).status_code == 304
    own_id = before["staff_user_id"]
    assert await db.get(StaffAvatar, own_id) is not None
    audit = list((await db.execute(select(TenantAuditEvent).where(
        TenantAuditEvent.actor_staff_user_id == own_id,
        TenantAuditEvent.action.in_(["staff_profile.updated", "staff_avatar.updated"]),
    ))).scalars())
    assert len(audit) == 2

    partner = Tenant(slug="profile-partner", display_name="Partner")
    db.add(partner)
    await db.flush()
    site = Storefront(tenant_id=partner.id, slug="main", display_name="Partner", status="active", is_default=True)
    db.add(site)
    await db.commit()
    other = await staff_token(async_client, db, username="profile-other", scope=TenantScope(tenant_id=partner.id, storefront_id=site.id))
    denied = await async_client.get(url, headers={**other, "If-None-Match": etag})
    assert denied.status_code == 404
    assert (await async_client.get("/api/manager/account/profile", headers=other)).json()["staff_user_id"] != own_id
    removed = await async_client.request("DELETE", "/api/manager/account/profile/avatar", headers=headers,
                                        json={"expected_updated_at": uploaded.json()["updated_at"]})
    assert removed.status_code == 200, removed.text
    assert removed.json()["avatar_url"] is None
    assert (await async_client.get(url, headers=headers)).status_code == 404
