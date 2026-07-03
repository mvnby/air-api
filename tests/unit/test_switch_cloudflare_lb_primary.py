import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/ha/switch_cloudflare_lb_primary.py"


spec = importlib.util.spec_from_file_location("switch_cloudflare_lb_primary", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _config(*, active="185.250.45.54", passive="193.47.42.213", allow_extra=False):
    return module.SwitchConfig(
        hostname="api.mvn.by",
        active_origin=active,
        passive_origin=passive,
        host_header="api.mvn.by",
        monitor_path="/api/ready",
        monitor_method="GET",
        monitor_expected_code="200",
        require_adaptive_failover=True,
        require_session_affinity_off=True,
        allow_extra_default_pools=allow_extra,
    )


def _fixtures(*, default_pools=None, fallback_pool="pool-primary"):
    load_balancers = [
        {
            "id": "lb-api",
            "name": "api.mvn.by",
            "enabled": True,
            "default_pools": default_pools or ["pool-primary", "pool-standby"],
            "fallback_pool": fallback_pool,
            "adaptive_routing": {"failover_across_pools": True},
            "session_affinity": "none",
        }
    ]
    pools = [
        {
            "id": "pool-primary",
            "name": "mvn-api",
            "enabled": True,
            "monitor": "monitor-ready",
            "origins": [
                {
                    "name": "mvn-api",
                    "address": "185.250.45.54",
                    "enabled": True,
                    "header": {"Host": ["api.mvn.by"]},
                }
            ],
        },
        {
            "id": "pool-standby",
            "name": "zakup",
            "enabled": True,
            "monitor": "monitor-ready",
            "origins": [
                {
                    "name": "zakup",
                    "address": "193.47.42.213",
                    "enabled": True,
                    "header": {"Host": ["api.mvn.by"]},
                }
            ],
        },
        {
            "id": "pool-extra",
            "name": "extra",
            "enabled": True,
            "monitor": "monitor-ready",
            "origins": [{"name": "extra", "address": "203.0.113.10", "enabled": True}],
        },
    ]
    monitors = [
        {
            "id": "monitor-ready",
            "name": "mvn-api-ready",
            "type": "https",
            "method": "GET",
            "path": "/api/ready",
            "expected_codes": "200",
        }
    ]
    return load_balancers, pools, monitors


def test_build_switch_plan_noops_when_primary_order_already_matches():
    load_balancers, pools, monitors = _fixtures()

    plan = module.build_switch_plan(
        load_balancers=load_balancers,
        pools=pools,
        monitors=monitors,
        config=_config(),
    )

    assert not plan.needs_update
    assert plan.patch_payload == {}
    assert plan.desired_default_pools == ["pool-primary", "pool-standby"]
    assert plan.desired_fallback_pool == "pool-primary"


def test_build_switch_plan_promotes_zakup_pool_order_and_fallback():
    load_balancers, pools, monitors = _fixtures()

    plan = module.build_switch_plan(
        load_balancers=load_balancers,
        pools=pools,
        monitors=monitors,
        config=_config(active="193.47.42.213", passive="185.250.45.54"),
    )

    assert plan.needs_update
    assert plan.active_pool_name == "zakup"
    assert plan.passive_pool_name == "mvn-api"
    assert plan.patch_payload == {
        "default_pools": ["pool-standby", "pool-primary"],
        "fallback_pool": "pool-standby",
    }


def test_build_switch_plan_updates_only_fallback_when_order_matches():
    load_balancers, pools, monitors = _fixtures(
        default_pools=["pool-standby", "pool-primary"],
        fallback_pool="pool-primary",
    )

    plan = module.build_switch_plan(
        load_balancers=load_balancers,
        pools=pools,
        monitors=monitors,
        config=_config(active="193.47.42.213", passive="185.250.45.54"),
    )

    assert plan.patch_payload == {"fallback_pool": "pool-standby"}


def test_build_switch_plan_rejects_extra_pools_by_default():
    load_balancers, pools, monitors = _fixtures(
        default_pools=["pool-primary", "pool-standby", "pool-extra"],
    )

    with pytest.raises(module.AuditFailure, match="extra pools"):
        module.build_switch_plan(
            load_balancers=load_balancers,
            pools=pools,
            monitors=monitors,
            config=_config(),
        )


def test_build_switch_plan_preserves_extra_pools_when_allowed():
    load_balancers, pools, monitors = _fixtures(
        default_pools=["pool-primary", "pool-standby", "pool-extra"],
    )

    plan = module.build_switch_plan(
        load_balancers=load_balancers,
        pools=pools,
        monitors=monitors,
        config=_config(active="193.47.42.213", passive="185.250.45.54", allow_extra=True),
    )

    assert plan.patch_payload["default_pools"] == ["pool-standby", "pool-primary", "pool-extra"]


def test_main_without_confirm_prints_plan_but_does_not_patch(monkeypatch):
    calls = []
    load_balancers, pools, monitors = _fixtures()

    def fake_fetch(**kwargs):
        calls.append(("fetch", kwargs))
        return load_balancers, pools, monitors

    def fake_patch(path, token, payload):
        calls.append(("patch", path, token, payload))
        return {}

    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "zone")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setattr(module, "fetch_cloudflare_config", fake_fetch)
    monkeypatch.setattr(module, "_api_patch", fake_patch)

    assert module.main(["--active-origin", "193.47.42.213", "--passive-origin", "185.250.45.54"]) == 0

    assert [call[0] for call in calls] == ["fetch"]
    assert calls[0][1]["token"] == "secret-token"


def test_main_with_confirm_patches_minimal_payload(monkeypatch):
    calls = []
    load_balancers, pools, monitors = _fixtures()

    def fake_fetch(**kwargs):
        calls.append(("fetch", kwargs))
        return load_balancers, pools, monitors

    def fake_patch(path, token, payload):
        calls.append(("patch", path, token, payload))
        updated = dict(load_balancers[0])
        updated.update(payload)
        return updated

    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "zone")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setattr(module, "fetch_cloudflare_config", fake_fetch)
    monkeypatch.setattr(module, "_api_patch", fake_patch)

    assert (
        module.main(
            [
                "--active-origin",
                "193.47.42.213",
                "--passive-origin",
                "185.250.45.54",
                "--confirm",
            ]
        )
        == 0
    )

    assert calls[1] == (
        "patch",
        "/zones/zone/load_balancers/lb-api",
        "secret-token",
        {"default_pools": ["pool-standby", "pool-primary"], "fallback_pool": "pool-standby"},
    )


def test_cloudflare_patch_403_explains_write_permission():
    message = module._format_cloudflare_patch_error(
        "/zones/zone/load_balancers/lb-api",
        403,
        '{"success":false,"errors":[{"code":10000,"message":"Authentication error"}]}',
    )

    assert "Authentication error" in message
    assert "Zone / Load Balancers / Edit" in message
    assert "default_pools" in message
    assert "fallback_pool" in message
