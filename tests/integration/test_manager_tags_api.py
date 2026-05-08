import pytest

from core.config import settings


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_create_tag_group_returns_empty_tags(async_client):
    headers = await _auth_headers(async_client)

    response = await async_client.post(
        "/api/manager/tags/groups",
        headers=headers,
        json={
            "title": "Sentry Regression Group",
            "slug": "sentry-regression-group",
            "is_public": True,
            "color": "secondary",
            "allow_multiple": False,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["slug"] == "sentry-regression-group"
    assert data["tags"] == []
