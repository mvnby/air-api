from datetime import timedelta
from io import BytesIO
import pytest
from PIL import Image
from core.security import create_access_token
from models import DocumentLegalEntity, StaffUser, Storefront, Tenant, TenantMembership
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage

BASE = "/api/manager/document-system"


async def identity(db, suffix, role):
    tenant = Tenant(
        slug=f"scan-{suffix}", display_name=suffix, status="active", is_system=False
    )
    db.add(tenant)
    await db.flush()
    storefront = Storefront(
        tenant_id=tenant.id,
        slug="main",
        display_name=suffix,
        status="active",
        is_default=True,
    )
    user = StaffUser(
        display_name=suffix,
        username=f"scan-{suffix}",
        status="active",
        roles=[role],
        primary_role=role,
    )
    db.add_all([storefront, user])
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant.id, staff_user_id=user.id, role=role, status="active"
        )
    )
    entity = DocumentLegalEntity(
        tenant_id=tenant.id, slug="main", display_name=suffix, is_default=True
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    token = create_access_token(
        {
            "sub": user.username,
            "staff_user_id": user.id,
            "auth_version": user.auth_version,
            "auth_source": "scan-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    return {"Authorization": f"Bearer {token}"}, entity, user


@pytest.mark.asyncio
async def test_partner_upload_manager_read_foreign_denial(
    async_client, db, monkeypatch, tmp_path
):
    storage = LocalPrivateAttachmentStorage(tmp_path / "scan-private")
    monkeypatch.setattr(
        "services.legal_entity_attachment_service.get_private_attachment_storage",
        lambda *args: storage,
    )
    headers, entity, user = await identity(db, "owner", "owner")
    other, foreign, _ = await identity(db, "foreign", "owner")
    output = BytesIO()
    Image.new("RGB", (4, 4), "white").save(output, format="PNG")
    content = output.getvalue()
    response = await async_client.post(
        f"{BASE}/legal-entities/{entity.id}/registration-certificates",
        headers=headers,
        files={"file": ("../../test.exe", content, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["mime_type"] == "image/png" and item["filename"] == "test.png"
    assert "storage_key" not in item and "provider" not in item
    for path in [
        f"/legal-entities/{entity.id}/registration-certificates",
        f"/registration-certificates/{item['id']}/download",
    ]:
        denied = await async_client.get(BASE + path, headers=other)
        assert denied.status_code == 404, denied.text
    denied = await async_client.put(
        f"{BASE}/registration-certificates/{item['id']}/current", headers=other
    )
    assert denied.status_code == 404, denied.text
    denied = await async_client.post(
        f"{BASE}/legal-entities/{entity.id}/registration-certificates",
        headers=other,
        files={"file": ("x.png", content, "image/png")},
    )
    assert denied.status_code == 404, denied.text
    memberships = (
        (
            await db.execute(
                __import__("sqlalchemy")
                .select(TenantMembership)
                .where(TenantMembership.staff_user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    memberships[0].role = "manager"
    user.primary_role = "manager"
    user.roles = ["manager"]
    db.add_all([memberships[0], user])
    await db.commit()
    response = await async_client.get(
        f"{BASE}/registration-certificates/{item['id']}/download", headers=headers
    )
    assert response.status_code == 200 and response.content == content
    assert response.headers["cache-control"] == "private, no-store"
    response = await async_client.post(
        f"{BASE}/legal-entities/{entity.id}/registration-certificates",
        headers=headers,
        files={"file": ("x.png", content, "image/png")},
    )
    assert response.status_code == 403, response.text
    response = await async_client.put(
        f"{BASE}/registration-certificates/{item['id']}/current", headers=headers
    )
    assert response.status_code == 403, response.text
