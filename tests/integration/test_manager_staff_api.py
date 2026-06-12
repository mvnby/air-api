import pytest

from core.config import settings


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    return {"Authorization": f"Bearer {login_resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_manager_staff_crud_hides_password_hash_and_changes_password(async_client, db):
    headers = await _auth_headers(async_client)

    create_response = await async_client.post(
        "/api/manager/staff",
        json={
            "display_name": "Офис Менеджер",
            "primary_role": "manager",
            "status": "active",
            "username": "office",
            "password": "secret123",
            "phone": "+375291112233",
            "email": "office@example.com",
            "telegram_id": 123456,
            "telegram_username": "office_mvn",
            "is_assignable_installer": False,
        },
        headers=headers,
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["primary_role"] == "manager"
    assert created["has_password"] is True
    assert created["is_assignable_installer"] is False
    assert "password_hash" not in created

    login_response = await async_client.post(
        "/login/access-token",
        data={"username": "office", "password": "secret123"},
    )
    assert login_response.status_code == 200

    patch_response = await async_client.patch(
        f"/api/manager/staff/{created['id']}",
        json={
            "password": "newsecret123",
            "primary_role": "owner",
            "is_assignable_installer": True,
            "default_rate": 250,
        },
        headers=headers,
    )

    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["primary_role"] == "owner"
    assert patched["is_assignable_installer"] is True
    assert patched["legacy_installer_id"] is not None

    old_login = await async_client.post(
        "/login/access-token",
        data={"username": "office", "password": "secret123"},
    )
    assert old_login.status_code == 400

    new_login = await async_client.post(
        "/login/access-token",
        data={"username": "office", "password": "newsecret123"},
    )
    assert new_login.status_code == 200

    list_response = await async_client.get("/api/manager/staff", headers=headers)
    assert list_response.status_code == 200
    item = list_response.json()["items"][0]
    assert item["display_name"] == "Офис Менеджер"
    assert "password_hash" not in item
