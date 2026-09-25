"""Owner-approved installation draft template, independent of any tenant rows.

The values here are the one source for canonical setup, an explicitly reviewed
partner reset, and the existing detached partner onboarding copy. Publishing a
book remains a separate, explicit operation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


SEED_VERSION = "installation-grid-2026-09-25-v1"


@dataclass(frozen=True)
class InstallationGridRule:
    code: str
    name: str
    rule_type: str
    unit: str
    price: int
    optional: bool = False

    def fields(self) -> dict[str, Any]:
        return {
            "rule_type": self.rule_type,
            "name": self.name,
            "line_template": "{name}",
            "unit": self.unit,
            "unit_price": float(self.price),
            "component_code": self.code,
            "is_optional": self.optional,
            "is_favorite": False,
            "is_active": True,
        }


@dataclass(frozen=True)
class InstallationGridTariff:
    code: str
    label: str
    category: str
    power_range: str
    match: dict[str, Any]
    base_price: int
    included_route_meters: int
    included_holes: dict[str, int]
    rules: tuple[InstallationGridRule, ...]

    def fields(self) -> dict[str, Any]:
        return {
            "service_kind": "installation",
            "selector_label": self.label,
            "estimate_template": self.label,
            "short_name": self.label,
            "full_description": self.label,
            "category": self.category,
            "power_range": self.power_range,
            "base_price": self.base_price,
            "installation_code": self.code,
            "installation_match": deepcopy(self.match),
            "installation_price_mode": "fixed",
            "included_holes_by_type": deepcopy(self.included_holes),
            "included_route_meters": float(self.included_route_meters),
            "is_active": True,
            "comment": f"Approved {SEED_VERSION}; Manager edits remain tenant-local",
        }


def _rules(*, route_extra: int | None) -> tuple[InstallationGridRule, ...]:
    rules: list[InstallationGridRule] = []
    if route_extra is not None:
        rules.append(InstallationGridRule(
            "route.extra_m", "Дополнительный метр трассы",
            "per_meter_over_included", "м", route_extra,
        ))
    rules.extend((
        InstallationGridRule(
            "hole.through_thin.extra", "Дополнительное отверстие до 20 см",
            "per_hole_manual", "шт", 30,
        ),
        InstallationGridRule(
            "hole.through_thick.extra", "Дополнительное отверстие свыше 20 до 80 см",
            "per_hole_manual", "шт", 70,
        ),
        InstallationGridRule(
            "pump.package", "Дренажный насос с поставкой и монтажом",
            "per_unit_manual", "шт", 280, True,
        ),
        InstallationGridRule(
            "access.scaffold", "Леса — предварительный ориентир",
            "fixed_once", "шт", 100, True,
        ),
        InstallationGridRule(
            "access.lift", "Вышка, минимум 4 часа — предварительный ориентир",
            "fixed_once", "шт", 350, True,
        ),
    ))
    return tuple(rules)


def canonical_installation_grid() -> tuple[InstallationGridTariff, ...]:
    """Return fresh specifications; no mutable JSON is shared between tenants."""
    result: list[InstallationGridTariff] = []

    def add(
        *, key: str, label: str, category: str, power_range: str,
        product_kind: str = "complete_split_system", indoor_type: str | None,
        strategy: str, base: int, prelaid: int, route: int, extra: int,
        capacity_min: str | None = None, capacity_max: str | None = None,
        min_inclusive: bool = True, max_inclusive: bool = True,
    ) -> None:
        for work_kind, price, included_route in (
            ("standard", base, route), ("prelaid_route", prelaid, 0),
        ):
            matcher: dict[str, Any] = {
                "product_kind": product_kind,
                "indoor_type": indoor_type,
                "work_kind": work_kind,
                "match_strategy": strategy,
            }
            if capacity_min is not None:
                matcher["capacity_min_kw"] = capacity_min
                matcher["capacity_min_inclusive"] = min_inclusive
            if capacity_max is not None:
                matcher["capacity_max_kw"] = capacity_max
                matcher["capacity_max_inclusive"] = max_inclusive
            result.append(InstallationGridTariff(
                code=f"installation.{key}.{work_kind}.v20260925",
                label=f"{label} — {'готовая трасса' if work_kind == 'prelaid_route' else 'обычный монтаж'}",
                category=category,
                power_range=power_range,
                match=matcher,
                base_price=price,
                included_route_meters=included_route,
                included_holes={"shared_pass_through": 1} if work_kind == "standard" else {},
                # A new route on prelaid work has no approved fixed price.
                rules=_rules(route_extra=extra if work_kind == "standard" else None),
            ))

    add(key="wall.small", label="Настенный до 4,2 кВт", category="Wall",
        power_range="до 4,2 кВт", indoor_type="wall", strategy="capacity_only",
        base=600, prelaid=300, route=3, extra=50,
        capacity_max="4.2")
    add(key="wall.middle", label="Настенный свыше 4,2 и менее 8 кВт", category="Wall",
        power_range="свыше 4,2 и менее 8 кВт", indoor_type="wall", strategy="capacity_only",
        base=750, prelaid=450, route=3, extra=65,
        capacity_min="4.2", min_inclusive=False,
        capacity_max="8.0", max_inclusive=False)
    add(key="wall.large", label="Настенный от 8 до 10,55 кВт", category="Wall",
        power_range="8–10,55 кВт, подтверждённое покрытие", indoor_type="wall",
        strategy="capacity_only", base=960, prelaid=576, route=3, extra=85,
        capacity_min="8.0", capacity_max="10.55")
    add(key="console.small", label="Консольный до 4,2 кВт", category="Console",
        power_range="до 4,2 кВт", indoor_type="console", strategy="capacity_only",
        base=600, prelaid=300, route=3, extra=50, capacity_max="4.2")
    add(key="console.middle", label="Консольный свыше 4,2 и менее 8 кВт", category="Console",
        power_range="свыше 4,2 и менее 8 кВт", indoor_type="console", strategy="capacity_only",
        base=750, prelaid=450, route=3, extra=65,
        capacity_min="4.2", min_inclusive=False,
        capacity_max="8.0", max_inclusive=False)
    for key, label, category, indoor_type in (
        ("cassette", "Кассетный", "Cassette", "cassette"),
        ("duct", "Канальный", "Duct", "duct"),
        ("floor_ceiling", "Напольно-потолочный", "FloorCeiling", "floor_ceiling"),
        ("column", "Колонный", "Column", "column"),
    ):
        add(key=key, label=label, category=category, power_range="All",
            indoor_type=indoor_type, strategy="type_only", base=1500,
            prelaid=900, route=5, extra=85)
    add(key="multi", label="Мультисплит, за внутренний блок", category="Multi",
        power_range="All", product_kind="multi_split_system", indoor_type=None,
        strategy="type_only", base=500, prelaid=300, route=3, extra=50)
    return tuple(result)
