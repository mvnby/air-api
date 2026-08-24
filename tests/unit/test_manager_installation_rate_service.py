from sqlmodel import delete, select

from models import InstallationRate
from schemas_manager_installation_rates import (
    ManagerInstallationRateSelectionStatus,
    ManagerInstallationRateUpdatePayload,
)
from services.manager_installation_rate_service import ManagerInstallationRateService
from services.installation_service import InstallationService


def _rate(
    category: str,
    *,
    power_range: str = "All",
    base_price: int = 1200,
    is_fixed: bool = False,
) -> InstallationRate:
    return InstallationRate(
        id=1,
        category=category,
        power_range=power_range,
        base_price=base_price,
        extra_pipe_price=85,
        included_pipe_meters=3,
        is_fixed=is_fixed,
    )


def test_manager_rate_projection_explains_public_resolver_statuses():
    wall = ManagerInstallationRateService._to_response(
        _rate(
            "Wall",
            power_range="area-20, area-25, area-35",
            base_price=600,
            is_fixed=True,
        )
    )
    duct = ManagerInstallationRateService._to_response(_rate("Duct", base_price=1500))
    legacy = ManagerInstallationRateService._to_response(_rate("Cassette/Ceiling"))
    unsupported = ManagerInstallationRateService._to_response(
        _rate("Multisplit", base_price=500)
    )

    assert wall.equipment_label == "Настенная сплит-система"
    assert wall.power_label == "2–4 кВт"
    assert (
        wall.selection_status is ManagerInstallationRateSelectionStatus.automatic_fixed
    )
    assert wall.title == "Монтаж настенной сплит-системы"

    assert duct.equipment_label == "Канальный кондиционер"
    assert (
        duct.selection_status
        is ManagerInstallationRateSelectionStatus.matched_manual_quote
    )
    assert duct.title == "Монтаж канального кондиционера"

    assert (
        legacy.selection_status
        is ManagerInstallationRateSelectionStatus.legacy_manual_quote
    )
    assert (
        unsupported.selection_status
        is ManagerInstallationRateSelectionStatus.unsupported
    )


def test_fixed_wall_rate_without_capacity_coverage_is_not_presented_as_automatic():
    all_power = ManagerInstallationRateService._to_response(
        _rate("Wall", power_range="All", is_fixed=True)
    )
    unknown_range = ManagerInstallationRateService._to_response(
        _rate("Wall", power_range="unmapped", is_fixed=True)
    )

    assert (
        all_power.selection_status is ManagerInstallationRateSelectionStatus.unsupported
    )
    assert (
        unknown_range.selection_status
        is ManagerInstallationRateSelectionStatus.unsupported
    )
    assert "безопасного правила" in all_power.selection_note


async def test_manager_rate_update_changes_only_editable_public_fields(db):
    rate = InstallationRate(
        category="Cassette",
        power_range="All",
        base_price=1200,
        extra_pipe_price=85,
        included_pipe_meters=3,
        is_fixed=False,
        comment="old",
    )
    db.add(rate)
    await db.commit()
    await db.refresh(rate)

    updated = await ManagerInstallationRateService.update_rate(
        db,
        rate_id=int(rate.id),
        payload=ManagerInstallationRateUpdatePayload(
            base_price=1500,
            extra_pipe_price=90,
            included_pipe_meters=4,
            comment="  after survey  ",
        ),
    )

    assert updated.base_price == 1500
    assert updated.extra_pipe_price == 90
    assert updated.included_pipe_meters == 4
    assert updated.comment == "after survey"
    assert updated.category == "Cassette"
    assert updated.power_range == "All"
    assert updated.is_fixed is False


async def test_fresh_installation_rate_seed_uses_distinct_public_quote_prices(db):
    await db.execute(delete(InstallationRate))
    await db.commit()

    await InstallationService.seed_defaults(db)

    result = await db.execute(select(InstallationRate))
    rates = {
        (rate.category, rate.power_range): rate.base_price
        for rate in result.scalars().all()
    }
    assert rates[("Cassette", "All")] == 1500
    assert rates[("Duct", "All")] == 1500
    assert rates[("Ceiling", "All")] == 1400
    assert ("Cassette/Ceiling", "All") not in rates
