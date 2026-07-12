import pytest

from models import GlobalConfig


@pytest.mark.asyncio
async def test_public_config_exposes_only_storefront_keys(async_client, db):
    db.add_all(
        [
            GlobalConfig(key="phone", value="+375 29 000-00-00"),
            GlobalConfig(key="work_hours", value="Пн-Пт 09:00-18:00"),
            GlobalConfig(key="install_discount", value="100"),
            GlobalConfig(key="supplier_default_spreadsheet_id", value="private-sheet"),
            GlobalConfig(key="catalog_static_rebuild_last_error", value="internal-error"),
        ]
    )
    await db.commit()

    response = await async_client.get("/api/v1/config")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "phone": "+375 29 000-00-00",
        "work_hours": "Пн-Пт 09:00-18:00",
        "install_discount": "100",
    }
