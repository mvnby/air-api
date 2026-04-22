import pytest

from models import Service, ServiceTariff, ServiceTariffRule
from schemas import (
    ManagerEstimateRuleInputPayload,
    ManagerInstallEstimateCalculatePayload,
    ManagerInstallEstimateSavePayload,
    ManagerServiceEstimateOrderLinesMode,
)
from services.service_estimate_service import ServiceEstimateService


@pytest.mark.asyncio
async def test_calculate_install_estimate_with_rules(db):
    linked_service = Service(
        title="Установка дренажной помпы",
        slug="drain-pump",
        category="installation_option",
        base_price=180,
        is_active=True,
    )
    db.add(linked_service)
    await db.commit()
    await db.refresh(linked_service)

    tariff = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж настенного до 3.5 кВт",
        estimate_template="Монтаж сплит-системы настенного типа мощностью до 3,5 кВт, включая расходные материалы",
        category="Wall",
        power_range="12",
        base_price=500,
        included_route_meters=3.0,
    )
    db.add(tariff)
    await db.commit()
    await db.refresh(tariff)

    db.add(
        ServiceTariffRule(
            tariff_id=tariff.id,
            rule_type="per_meter_over_included",
            name="Дополнительная трасса",
            line_template="доп. трасса {qty} {unit}",
            unit="м",
            unit_price=40,
            is_optional=False,
            is_active=True,
            sort_order=10,
        )
    )
    db.add(
        ServiceTariffRule(
            tariff_id=tariff.id,
            rule_type="per_hole_manual",
            name="Дополнительные отверстия",
            line_template="{extra_holes_count} доп. отверстий",
            unit="шт",
            unit_price=70,
            is_optional=False,
            is_active=True,
            sort_order=20,
        )
    )
    addon_rule = ServiceTariffRule(
        tariff_id=tariff.id,
        rule_type="per_unit_manual",
        name="Дренажная помпа",
        line_template="{name} ({qty} {unit})",
        unit="шт",
        unit_price=180,
        service_id=linked_service.id,
        is_optional=True,
        is_active=True,
        sort_order=30,
    )
    db.add(addon_rule)
    await db.commit()
    await db.refresh(addon_rule)

    payload = ManagerInstallEstimateCalculatePayload(
        tariff_id=tariff.id,
        route_length_m=6,
        quantity=1,
        extra_holes_count=1,
        rule_inputs=[ManagerEstimateRuleInputPayload(rule_id=addon_rule.id, qty=1)],
        discount_amount=50,
    )

    result = await ServiceEstimateService.calculate_install_estimate(db, payload)

    assert result.tariff.id == tariff.id
    assert result.subtotal == 870
    assert result.discount_amount == 50
    assert result.total == 820
    assert [line.source_type for line in result.lines] == ["base", "rule", "rule", "rule"]
    assert result.rule_lines[-1].service_id == linked_service.id


@pytest.mark.asyncio
async def test_create_and_get_install_estimate_snapshot(db):
    tariff = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж настенного 07-09",
        estimate_template="Стандартный монтаж кондиционера, включая расходные материалы",
        category="Wall",
        power_range="07-09",
        base_price=450,
        included_route_meters=3.0,
    )
    db.add(tariff)
    await db.commit()
    await db.refresh(tariff)

    meter_rule = ServiceTariffRule(
        tariff_id=tariff.id,
        rule_type="per_meter_over_included",
        name="Доп. трасса",
        line_template="трасса {qty} {unit}",
        unit="м",
        unit_price=35,
        is_optional=False,
        is_active=True,
        sort_order=10,
    )
    db.add(meter_rule)
    await db.commit()
    await db.refresh(meter_rule)

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
    assert created.tariff is not None
    assert created.tariff.id == tariff.id

    listed = await ServiceEstimateService.list_estimates(db, page=1, limit=20)
    assert listed.total == 1
    assert listed.items[0].id == created.id

    detailed = await ServiceEstimateService.get_estimate_order_lines(
        db,
        created.id,
        mode=ManagerServiceEstimateOrderLinesMode.detailed,
    )
    assert detailed.estimate_id == created.id
    assert detailed.mode == "detailed"
    assert len(detailed.services) >= 1

    collapsed = await ServiceEstimateService.get_estimate_order_lines(
        db,
        created.id,
        mode=ManagerServiceEstimateOrderLinesMode.collapsed,
    )
    assert collapsed.mode == "collapsed"
    assert len(collapsed.services) == 1
    assert collapsed.services[0].price == round(created.total)
    assert "включая расходные материалы" in collapsed.services[0].title.lower()

    deleted = await ServiceEstimateService.delete_estimate(db, created.id)
    assert "deleted" in deleted.message.lower()

    listed_after_delete = await ServiceEstimateService.list_estimates(db, page=1, limit=20)
    assert listed_after_delete.total == 0
