from models import FeatureRule
from services.feature_rule_engine import get_spec_value, matches_all_rules, matches_rule


def _rule(operator: str, target_value=None, *, spec_key: str = "area_m2") -> FeatureRule:
    return FeatureRule(
        id=1,
        feature_id=1,
        spec_key=spec_key,
        operator=operator,
        target_value=target_value,
        is_active=True,
        sort_order=0,
    )


def test_rule_engine_supports_nested_and_typed_specs():
    specs = {
        "performance": {"seer": "7,1"},
        "__typed_specs": {"noise_db": {"value": 19}},
    }

    assert get_spec_value(specs, "performance.seer") == "7,1"
    assert get_spec_value(specs, "noise_db") == 19


def test_rule_engine_supports_declared_operators():
    specs = {
        "area_m2": "35",
        "mode": "Inverter",
        "features": ["wifi", "quiet"],
        "description": "WiFi control included",
    }

    assert matches_rule(specs, _rule("eq", "inverter", spec_key="mode"))
    assert matches_rule(specs, _rule("neq", "on-off", spec_key="mode"))
    assert matches_rule(specs, _rule("gt", 30))
    assert matches_rule(specs, _rule("gte", 35))
    assert matches_rule(specs, _rule("lt", 40))
    assert matches_rule(specs, _rule("lte", 35))
    assert matches_rule(specs, _rule("in", ["on-off", "INVERTER"], spec_key="mode"))
    assert matches_rule(specs, _rule("contains", "quiet", spec_key="features"))
    assert matches_rule(specs, _rule("contains", "wifi", spec_key="description"))
    assert matches_rule(specs, _rule("exists", True, spec_key="mode"))
    assert matches_rule(specs, _rule("exists", False, spec_key="missing"))


def test_all_rules_requires_at_least_one_active_rule_and_uses_and_semantics():
    specs = {"area_m2": 35, "mode": "inverter"}
    rules = [_rule("gte", 30), _rule("eq", "inverter", spec_key="mode")]
    assert matches_all_rules(specs, rules)

    rules.append(_rule("lt", 30))
    assert not matches_all_rules(specs, rules)
    assert not matches_all_rules(specs, [])
