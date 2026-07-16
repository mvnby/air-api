import pytest

from models import ServiceTariff
from services.tariffs_service import TariffsService


def test_build_quick_add_title_enriches_generic_installation_tariff():
    tariff = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж настенного кондиционера",
        estimate_template="Монтаж кондиционера, включая расходные материалы",
        short_name="Монтаж настенного кондиционера",
        full_description="Монтаж кондиционера, включая расходные материалы",
        category="Wall",
        power_range="12",
        base_price=500,
        included_route_meters=3,
    )

    assert TariffsService.build_quick_add_title(tariff) == (
        "Монтаж настенного кондиционера, мощностью до 3,5 кВт, включая трассу длиной до 3 м"
    )


def test_build_quick_add_title_keeps_specific_template_without_duplicate_route():
    tariff = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж настенного кондиционера до 3,5 кВт с трассой до 3 м",
        estimate_template="Монтаж настенного кондиционера до 3,5 кВт с трассой до 3 м",
        category="Wall",
        power_range="12",
        base_price=500,
        included_route_meters=3,
    )

    assert TariffsService.build_quick_add_title(tariff) == "Монтаж настенного кондиционера до 3,5 кВт с трассой до 3 м"


def test_build_quick_add_title_enriches_pre_install_tariff_with_route():
    tariff = ServiceTariff(
        service_kind="pre_install",
        selector_label="Закладка коммуникаций под кондиционер",
        estimate_template="Закладка межблочной трассы под кондиционер, включая материалы",
        category="Wall",
        power_range="07-12",
        base_price=500,
        included_route_meters=3,
    )

    assert TariffsService.build_quick_add_title(tariff) == (
        "Закладка коммуникаций под кондиционер, мощностью до 3,5 кВт, включая трассу длиной до 3 м"
    )


def test_build_quick_add_title_does_not_add_route_for_repair_tariff():
    tariff = ServiceTariff(
        service_kind="repair",
        selector_label="Ремонт кондиционера",
        estimate_template="Ремонт кондиционера",
        category="repair",
        power_range="",
        base_price=150,
        included_route_meters=3,
    )

    assert TariffsService.build_quick_add_title(tariff) == "Ремонт кондиционера"


@pytest.mark.asyncio
async def test_list_quick_add_tariffs_filters_active_search_and_kind(db):
    active_installation = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж настенного кондиционера",
        estimate_template="Монтаж кондиционера, включая расходные материалы",
        short_name="Монтаж настенного кондиционера",
        full_description="Монтаж кондиционера, включая расходные материалы",
        category="Wall",
        power_range="12",
        base_price=500,
        included_route_meters=3,
        is_active=True,
        sort_order=20,
    )
    active_maintenance = ServiceTariff(
        service_kind="maintenance",
        selector_label="Обслуживание бытового кондиционера",
        estimate_template="Обслуживание бытового кондиционера",
        category="maintenance",
        power_range="12",
        base_price=120,
        included_route_meters=0,
        is_active=True,
        sort_order=10,
    )
    active_dismantling = ServiceTariff(
        service_kind="dismantling",
        selector_label="Демонтаж настенного кондиционера",
        estimate_template="Демонтаж настенного кондиционера",
        category="Wall",
        power_range="12",
        base_price=100,
        included_route_meters=0,
        is_active=True,
        sort_order=1,
    )
    active_repair = ServiceTariff(
        service_kind="repair",
        selector_label="Ремонт кондиционера",
        estimate_template="Ремонт кондиционера",
        category="repair",
        power_range="",
        base_price=150,
        included_route_meters=0,
        is_active=True,
        sort_order=2,
    )
    active_pre_install = ServiceTariff(
        service_kind="pre_install",
        selector_label="Закладка коммуникаций под кондиционер",
        estimate_template="Закладка межблочной трассы под кондиционер, включая материалы",
        category="Wall",
        power_range="07-12",
        base_price=500,
        included_route_meters=3,
        is_active=True,
        sort_order=3,
    )
    inactive_installation = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж архивный",
        estimate_template="Монтаж архивный",
        category="Wall",
        power_range="12",
        base_price=1,
        included_route_meters=3,
        is_active=False,
        sort_order=1,
    )
    db.add(active_installation)
    db.add(active_maintenance)
    db.add(active_dismantling)
    db.add(active_repair)
    db.add(active_pre_install)
    db.add(inactive_installation)
    await db.commit()

    result = await TariffsService.list_quick_add_tariffs(db, q="монт", limit=10)

    assert [item.tariff_id for item in result] == [active_installation.id, active_dismantling.id, active_repair.id]
    assert result[0].price == 500
    assert result[0].short_name == "Монтаж настенного кондиционера"
    assert result[0].full_description == "Монтаж кондиционера, включая расходные материалы"
    assert "мощностью до 3,5 кВт" in result[0].title

    maintenance = await TariffsService.list_quick_add_tariffs(db, service_kind="maintenance", q="обслуж", limit=10)
    assert [item.tariff_id for item in maintenance] == [active_maintenance.id]

    repair = await TariffsService.list_quick_add_tariffs(db, service_kind="repair", q="ремонт", limit=10)
    assert [item.tariff_id for item in repair] == [active_repair.id]
    assert repair[0].service_kind == "repair"

    pre_install = await TariffsService.list_quick_add_tariffs(db, service_kind="pre_install", q="заклад", limit=10)
    assert [item.tariff_id for item in pre_install] == [active_pre_install.id]
    assert pre_install[0].service_kind == "pre_install"
    assert "трассу длиной до 3 м" in pre_install[0].title
