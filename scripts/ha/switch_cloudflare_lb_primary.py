#!/usr/bin/env python3
"""Switch Cloudflare Load Balancer primary pool for MVN API HA.

The script changes only the load balancer's `default_pools` order and
`fallback_pool`. It deliberately does not edit pools, origins, monitors, or
host headers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ha.check_cloudflare_lb_config import (  # noqa: E402
    API_BASE_URL,
    AuditConfig,
    AuditFailure,
    _find_lb,
    _find_pool_by_origin,
    _id,
    _name,
    _normalize_bool,
    audit_configuration,
    fetch_cloudflare_config,
)


DEFAULT_HOSTNAME = "api.mvn.by"
DEFAULT_PRIMARY_ORIGIN = "185.250.45.54"
DEFAULT_STANDBY_ORIGIN = "193.47.42.213"
DEFAULT_HOST_HEADER = "api.mvn.by"
DEFAULT_MONITOR_PATH = "/api/ready"


@dataclass(frozen=True)
class SwitchConfig:
    hostname: str
    active_origin: str
    passive_origin: str
    host_header: str
    monitor_path: str
    monitor_method: str
    monitor_expected_code: str
    require_adaptive_failover: bool
    require_session_affinity_off: bool
    allow_extra_default_pools: bool


@dataclass(frozen=True)
class SwitchPlan:
    lb_id: str
    lb_name: str
    active_pool_id: str
    active_pool_name: str
    passive_pool_id: str
    passive_pool_name: str
    current_default_pools: list[str]
    desired_default_pools: list[str]
    current_fallback_pool: str
    desired_fallback_pool: str
    patch_payload: dict[str, Any]
    audit_messages: list[str]

    @property
    def needs_update(self) -> bool:
        return bool(self.patch_payload)


def log(stage: str, message: str) -> None:
    print(f"[cloudflare-lb-switch][{stage}] {message}")


def _clean(value: object | None) -> str:
    return str(value or "").strip()


def _api_patch(path: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{API_BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "mvn-ha-lb-switch/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AuditFailure(_format_cloudflare_patch_error(path, exc.code, body)) from exc
    except urllib.error.URLError as exc:
        raise AuditFailure(f"Cloudflare API request failed for {path}: {exc}") from exc

    if not response_payload.get("success"):
        errors = response_payload.get("errors") or []
        raise AuditFailure(f"Cloudflare API returned success=false for {path}: {errors}")
    result = response_payload.get("result") or {}
    if not isinstance(result, dict):
        raise AuditFailure(f"Cloudflare API result is not an object for {path}")
    return result


def _format_cloudflare_patch_error(path: str, status_code: int, body: str) -> str:
    message = f"Cloudflare API HTTP {status_code} for {path}: {body}"
    if status_code in {401, 403} and path.startswith("/zones/") and "/load_balancers/" in path:
        message += (
            " Required token permission for applying this switch: "
            "Zone / Load Balancers / Edit scoped to the mvn.by zone. "
            "The read-only audit token can inspect this configuration but cannot patch "
            "default_pools or fallback_pool."
        )
    return message


def _desired_default_pools(
    *,
    current_default_pools: Sequence[str],
    active_pool_id: str,
    passive_pool_id: str,
    allow_extra_default_pools: bool,
) -> list[str]:
    if len(current_default_pools) < 2:
        raise AuditFailure("load balancer has fewer than two default_pools")
    if not allow_extra_default_pools and len(current_default_pools) != 2:
        raise AuditFailure(f"default_pools has extra pools: {list(current_default_pools)}")

    extras = [
        pool_id
        for pool_id in current_default_pools
        if pool_id not in {active_pool_id, passive_pool_id}
    ]
    if extras and not allow_extra_default_pools:
        raise AuditFailure(f"default_pools has extra pools: {list(current_default_pools)}")
    return [active_pool_id, passive_pool_id, *extras]


def build_switch_plan(
    *,
    load_balancers: list[dict[str, Any]],
    pools: list[dict[str, Any]],
    monitors: list[dict[str, Any]],
    config: SwitchConfig,
) -> SwitchPlan:
    if config.active_origin == config.passive_origin:
        raise AuditFailure("active_origin and passive_origin must be different")

    lb = _find_lb(load_balancers, config.hostname)
    active_pool = _find_pool_by_origin(pools, config.active_origin)
    passive_pool = _find_pool_by_origin(pools, config.passive_origin)
    active_pool_id = _id(active_pool)
    passive_pool_id = _id(passive_pool)
    current_default_pools = [str(pool_id) for pool_id in (lb.get("default_pools") or [])]
    current_fallback_pool = str(lb.get("fallback_pool") or "")
    desired_default_pools = _desired_default_pools(
        current_default_pools=current_default_pools,
        active_pool_id=active_pool_id,
        passive_pool_id=passive_pool_id,
        allow_extra_default_pools=config.allow_extra_default_pools,
    )

    patched_lb = dict(lb)
    patched_lb["default_pools"] = desired_default_pools
    patched_lb["fallback_pool"] = active_pool_id
    audit_messages = audit_configuration(
        load_balancers=[patched_lb],
        pools=pools,
        monitors=monitors,
        config=AuditConfig(
            hostname=config.hostname,
            primary_origin=config.active_origin,
            standby_origin=config.passive_origin,
            host_header=config.host_header,
            monitor_path=config.monitor_path,
            monitor_method=config.monitor_method,
            monitor_expected_code=config.monitor_expected_code,
            require_adaptive_failover=config.require_adaptive_failover,
            require_session_affinity_off=config.require_session_affinity_off,
            allow_extra_default_pools=config.allow_extra_default_pools,
        ),
    )

    patch_payload: dict[str, Any] = {}
    if current_default_pools != desired_default_pools:
        patch_payload["default_pools"] = desired_default_pools
    if current_fallback_pool != active_pool_id:
        patch_payload["fallback_pool"] = active_pool_id

    return SwitchPlan(
        lb_id=_id(lb),
        lb_name=_name(lb),
        active_pool_id=active_pool_id,
        active_pool_name=_name(active_pool),
        passive_pool_id=passive_pool_id,
        passive_pool_name=_name(passive_pool),
        current_default_pools=current_default_pools,
        desired_default_pools=desired_default_pools,
        current_fallback_pool=current_fallback_pool,
        desired_fallback_pool=active_pool_id,
        patch_payload=patch_payload,
        audit_messages=audit_messages,
    )


def print_plan(plan: SwitchPlan) -> None:
    log("plan", f"load_balancer={plan.lb_name} id={plan.lb_id}")
    log("plan", f"active_pool={plan.active_pool_name} id={plan.active_pool_id}")
    log("plan", f"passive_pool={plan.passive_pool_name} id={plan.passive_pool_id}")
    log("plan", f"current_default_pools={plan.current_default_pools}")
    log("plan", f"desired_default_pools={plan.desired_default_pools}")
    log("plan", f"current_fallback_pool={plan.current_fallback_pool or '<empty>'}")
    log("plan", f"desired_fallback_pool={plan.desired_fallback_pool}")
    for message in plan.audit_messages:
        log("ok", message)
    if plan.needs_update:
        log("plan", f"patch_payload={json.dumps(plan.patch_payload, sort_keys=True)}")
    else:
        log("ok", "Cloudflare LB already matches requested active/passive order")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Switch Cloudflare LB default_pools/fallback_pool for MVN API active-passive routing."
    )
    parser.add_argument("--hostname", default=os.getenv("CF_LB_HOSTNAME", DEFAULT_HOSTNAME))
    parser.add_argument(
        "--active-origin",
        default=os.getenv("CF_LB_ACTIVE_ORIGIN")
        or os.getenv("API_PRIMARY_ORIGIN")
        or DEFAULT_PRIMARY_ORIGIN,
        help="Origin IP that should become primary in Cloudflare.",
    )
    parser.add_argument(
        "--passive-origin",
        default=os.getenv("CF_LB_PASSIVE_ORIGIN")
        or os.getenv("API_STANDBY_ORIGIN")
        or DEFAULT_STANDBY_ORIGIN,
        help="Origin IP that should become standby in Cloudflare.",
    )
    parser.add_argument("--host-header", default=os.getenv("CF_LB_HOST_HEADER", DEFAULT_HOST_HEADER))
    parser.add_argument("--monitor-path", default=os.getenv("CF_LB_MONITOR_PATH", DEFAULT_MONITOR_PATH))
    parser.add_argument("--monitor-method", default=os.getenv("CF_LB_MONITOR_METHOD", "GET"))
    parser.add_argument("--monitor-expected-code", default=os.getenv("CF_LB_MONITOR_EXPECTED_CODE", "200"))
    parser.add_argument(
        "--require-adaptive-failover",
        type=_normalize_bool,
        default=_normalize_bool(os.getenv("CF_LB_REQUIRE_ADAPTIVE_FAILOVER"), default=True),
    )
    parser.add_argument(
        "--require-session-affinity-off",
        type=_normalize_bool,
        default=_normalize_bool(os.getenv("CF_LB_REQUIRE_SESSION_AFFINITY_OFF"), default=True),
    )
    parser.add_argument(
        "--allow-extra-default-pools",
        type=_normalize_bool,
        default=_normalize_bool(os.getenv("CF_LB_ALLOW_EXTRA_DEFAULT_POOLS"), default=False),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually PATCH Cloudflare. Without this flag the script only prints the plan.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    token = _clean(os.getenv("CLOUDFLARE_API_TOKEN"))
    zone_id = _clean(os.getenv("CLOUDFLARE_ZONE_ID"))
    account_id = _clean(os.getenv("CLOUDFLARE_ACCOUNT_ID"))
    missing = [
        name
        for name, value in (
            ("CLOUDFLARE_API_TOKEN", token),
            ("CLOUDFLARE_ZONE_ID", zone_id),
            ("CLOUDFLARE_ACCOUNT_ID", account_id),
        )
        if not value
    ]
    if missing:
        log("fail", "missing Cloudflare credentials: " + ", ".join(missing))
        return 1

    config = SwitchConfig(
        hostname=args.hostname,
        active_origin=args.active_origin,
        passive_origin=args.passive_origin,
        host_header=args.host_header,
        monitor_path=args.monitor_path,
        monitor_method=args.monitor_method,
        monitor_expected_code=args.monitor_expected_code,
        require_adaptive_failover=args.require_adaptive_failover,
        require_session_affinity_off=args.require_session_affinity_off,
        allow_extra_default_pools=args.allow_extra_default_pools,
    )
    try:
        load_balancers, pools, monitors = fetch_cloudflare_config(
            token=token,
            zone_id=zone_id,
            account_id=account_id,
        )
        plan = build_switch_plan(
            load_balancers=load_balancers,
            pools=pools,
            monitors=monitors,
            config=config,
        )
        print_plan(plan)
        if not plan.needs_update:
            return 0
        if args.dry_run or not args.confirm:
            log("dry-run", "not patching Cloudflare; pass --confirm without --dry-run to apply this plan")
            return 0

        updated_lb = _api_patch(
            f"/zones/{zone_id}/load_balancers/{plan.lb_id}",
            token,
            plan.patch_payload,
        )
        audit_configuration(
            load_balancers=[updated_lb],
            pools=pools,
            monitors=monitors,
            config=AuditConfig(
                hostname=config.hostname,
                primary_origin=config.active_origin,
                standby_origin=config.passive_origin,
                host_header=config.host_header,
                monitor_path=config.monitor_path,
                monitor_method=config.monitor_method,
                monitor_expected_code=config.monitor_expected_code,
                require_adaptive_failover=config.require_adaptive_failover,
                require_session_affinity_off=config.require_session_affinity_off,
                allow_extra_default_pools=config.allow_extra_default_pools,
            ),
        )
    except AuditFailure as exc:
        log("fail", str(exc))
        return 1

    log("ok", "Cloudflare LB primary switch applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
