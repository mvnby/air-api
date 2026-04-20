import pytest

from models import InstallationRate, Service
from schemas import ManagerEstimateAddonPayload, ManagerInstallEstimateCalculatePayload, ManagerInstallEstimateSavePayload
from services.service_estimate_service import ServiceEstimateService


@pytest.mark.asyncio
async def test_calculate_install_estimate_with_modifiers_and_addons(db):
    tariff = InstallationRate(
        category="Wall",
        power_range="12",
        base_price=500,
        extra_pipe_price=40,
        included_pipe_meters=3,
        is_fixed=True,
    )
    addon_service = Service(
        title="Установка дренажной помпы",
        slug="drain-pump",
        category="installation_option",
        base_price=180,
        is_active=True,
    )
    db.add(tariff)
    db.add(addon_service)
    await db.commit()
    await db.refresh(tariff)
    await db.refresh(addon_service)

    payload = ManagerInstallEstimateCalculatePayload(
        category="Wall",
        power_range="12",
        route_length_m=6,
        quantity=1,
        extra_holes_count=1,
        extra_hole_price=70,
        addons=[ManagerEstimateAddonPayload(slug="drain-pump", qty=1)],
        discount_amount=50,
    )

    result = await ServiceEstimateService.calculate_install_estimate(db, payload)

    assert result.tariff_id == tariff.id
    assert result.extra_pipe_meters == 3
    assert result.subtotal == 870
    assert result.discount_amount == 50
    assert result.total == 820
    assert [line.source_type for line in result.lines] == ["base", "modifier", "modifier", "addon"]


@pytest.mark.asyncio
async def test_create_and_get_install_estimate_snapshot(db):
    tariff = InstallationRate(
        category="Wall",
        power_range="07-09",
        base_price=450,
        extra_pipe_price=35,
        included_pipe_meters=3,
        is_fixed=True,
    )
    db.add(tariff)
    await db.commit()
    await db.refresh(tariff)

    payload = ManagerInstallEstimateSavePayload(
        tariff_id=tariff.id,
        route_length_m=5,
        quantity=2,
        discount_amount=25,
        title="Смета тест",
    )

    created = await ServiceEstimateService.create_install_estimate(
        session=db,
        payload=payload,
        created_by="admin",
    )
    fetched = await ServiceEstimateService.get_estimate_by_id(db, created.id)

    assert created.id > 0
    assert created.title == "Смета тест"
    assert created.created_by == "admin"
    assert created.total == fetched.total
    assert len(created.lines) == len(fetched.lines)

    listed = await ServiceEstimateService.list_estimates(db, page=1, limit=20)
    assert listed.total == 1
    assert listed.items[0].id == created.id
