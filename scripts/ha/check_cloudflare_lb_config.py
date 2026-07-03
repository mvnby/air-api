#!/usr/bin/env python3
"""Read-only Cloudflare Load Balancer configuration audit for MVN API HA."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


API_BASE_URL = "https://api.cloudflare.com/client/v4"


class AuditFailure(Exception):
    pass


@dataclass(frozen=True)
class AuditConfig:
    hostname: str
    primary_origin: str
    standby_origin: str
    host_header: str
    monitor_path: str
    monitor_method: str
    monitor_expected_code: str
    require_adaptive_failover: bool
    require_session_affinity_off: bool
    allow_extra_default_pools: bool


def _log(stage: str, message: str) -> None:
    print(f"[cloudflare-lb][{stage}] {message}")


def _normalize_bool(value: str | bool | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean, got {value!r}")


def _api_get(path: str, token: str, params: dict[str, str] | None = None) -> Any:
    url = f"{API_BASE_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "mvn-ha-audit/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AuditFailure(_format_cloudflare_http_error(path, exc.code, body)) from exc
    except urllib.error.URLError as exc:
        raise AuditFailure(f"Cloudflare API request failed for {path}: {exc}") from exc

    if not payload.get("success"):
        errors = payload.get("errors") or []
        raise AuditFailure(f"Cloudflare API returned success=false for {path}: {errors}")
    return payload


def _format_cloudflare_http_error(path: str, status_code: int, body: str) -> str:
    details = _cloudflare_error_messages(body)
    message = f"Cloudflare API HTTP {status_code} for {path}"
    if details:
        message = f"{message}: {details}"
    else:
        message = f"{message}: {body}"

    if status_code in {401, 403}:
        hint = _cloudflare_token_permission_hint(path)
        if hint:
            message = f"{message}. {hint}"
    return message


def _cloudflare_error_messages(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return ""
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return ""
    messages = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        code = error.get("code")
        text = error.get("message")
        if code and text:
            messages.append(f"{code}: {text}")
        elif text:
            messages.append(str(text))
    return "; ".join(messages)


def _cloudflare_token_permission_hint(path: str) -> str:
    if path.startswith("/zones/") and "/load_balancers" in path:
        return (
            "Required token permissions: Zone / Load Balancers / Read scoped to "
            "the mvn.by zone, plus Account / Load Balancing: Monitors and Pools / Read "
            "scoped to the Cloudflare account."
        )
    if path.startswith("/accounts/") and "/load_balancers/" in path:
        return (
            "Required token permissions: Account / Load Balancing: Monitors and Pools / Read "
            "scoped to the Cloudflare account, plus Zone / Load Balancers / Read scoped "
            "to the mvn.by zone."
        )
    return ""


def _list_all(path: str, token: str) -> list[dict[str, Any]]:
    page = 1
    results: list[dict[str, Any]] = []
    while True:
        payload = _api_get(path, token, {"page": str(page), "per_page": "50"})
        page_results = payload.get("result") or []
        if not isinstance(page_results, list):
            raise AuditFailure(f"Cloudflare API result is not a list for {path}")
        results.extend(item for item in page_results if isinstance(item, dict))

        info = payload.get("result_info") or {}
        total_pages = int(info.get("total_pages") or 1)
        if page >= total_pages:
            return results
        page += 1


def fetch_cloudflare_config(*, token: str, zone_id: str, account_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    load_balancers = _list_all(f"/zones/{zone_id}/load_balancers", token)
    pools = _list_all(f"/accounts/{account_id}/load_balancers/pools", token)
    monitors = _list_all(f"/accounts/{account_id}/load_balancers/monitors", token)
    return load_balancers, pools, monitors


def _id(item: dict[str, Any]) -> str:
    return str(item.get("id") or "")


def _name(item: dict[str, Any]) -> str:
    return str(item.get("name") or "")


def _origin_address(origin: dict[str, Any]) -> str:
    return str(origin.get("address") or "").strip()


def _origin_enabled(origin: dict[str, Any]) -> bool:
    return bool(origin.get("enabled", True))


def _host_header_values(item: dict[str, Any]) -> set[str]:
    header = item.get("header")
    values: set[str] = set()
    if isinstance(header, dict):
        for key, raw in header.items():
            if str(key).lower() != "host":
                continue
            if isinstance(raw, list):
                values.update(str(value).strip() for value in raw if str(value).strip())
            elif raw:
                values.add(str(raw).strip())
    return values


def _find_lb(load_balancers: list[dict[str, Any]], hostname: str) -> dict[str, Any]:
    matches = [lb for lb in load_balancers if _name(lb) == hostname]
    if not matches:
        raise AuditFailure(f"load balancer not found for hostname {hostname!r}")
    if len(matches) > 1:
        raise AuditFailure(f"multiple load balancers found for hostname {hostname!r}")
    return matches[0]


def _find_pool_by_origin(pools: list[dict[str, Any]], address: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for pool in pools:
        origins = pool.get("origins") or []
        if not isinstance(origins, list):
            continue
        if any(isinstance(origin, dict) and _origin_address(origin) == address for origin in origins):
            matches.append(pool)
    if not matches:
        raise AuditFailure(f"pool not found for origin address {address}")
    if len(matches) > 1:
        names = ", ".join(_name(pool) or _id(pool) for pool in matches)
        raise AuditFailure(f"origin address {address} appears in multiple pools: {names}")
    return matches[0]


def _monitor_by_id(monitors: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_id(monitor): monitor for monitor in monitors if _id(monitor)}


def _check_origin(pool: dict[str, Any], address: str, host_header: str) -> None:
    origins = [origin for origin in (pool.get("origins") or []) if isinstance(origin, dict) and _origin_address(origin) == address]
    if len(origins) != 1:
        raise AuditFailure(f"pool {_name(pool)!r} should contain exactly one origin {address}, got {len(origins)}")
    origin = origins[0]
    if not _origin_enabled(origin):
        raise AuditFailure(f"origin {address} in pool {_name(pool)!r} is disabled")

    origin_headers = _host_header_values(origin)
    pool_headers = _host_header_values(pool)
    if host_header not in origin_headers and host_header not in pool_headers:
        raise AuditFailure(
            f"origin {address} in pool {_name(pool)!r} does not set Host header {host_header!r}"
        )


def _monitor_expected_codes_include(monitor: dict[str, Any], expected_code: str) -> bool:
    raw = monitor.get("expected_codes")
    if raw is None:
        return False
    if isinstance(raw, list):
        return expected_code in {str(item).strip() for item in raw}
    parts = str(raw).replace(",", " ").split()
    return expected_code in {part.strip() for part in parts}


def _check_pool_monitor(pool: dict[str, Any], monitors: dict[str, dict[str, Any]], config: AuditConfig) -> None:
    monitor_id = str(pool.get("monitor") or "")
    if not monitor_id:
        raise AuditFailure(f"pool {_name(pool)!r} has no monitor")
    monitor = monitors.get(monitor_id)
    if not monitor:
        raise AuditFailure(f"pool {_name(pool)!r} references missing monitor {monitor_id}")

    monitor_type = str(monitor.get("type") or "").lower()
    if monitor_type != "https":
        raise AuditFailure(f"monitor {_name(monitor)!r} type={monitor_type!r}, expected 'https'")
    monitor_method = str(monitor.get("method") or "GET").upper()
    if monitor_method != config.monitor_method.upper():
        raise AuditFailure(
            f"monitor {_name(monitor)!r} method={monitor_method!r}, expected {config.monitor_method!r}"
        )
    monitor_path = str(monitor.get("path") or "")
    if monitor_path != config.monitor_path:
        raise AuditFailure(
            f"monitor {_name(monitor)!r} path={monitor_path!r}, expected {config.monitor_path!r}"
        )
    if not _monitor_expected_codes_include(monitor, config.monitor_expected_code):
        raise AuditFailure(
            f"monitor {_name(monitor)!r} expected_codes={monitor.get('expected_codes')!r} "
            f"does not include {config.monitor_expected_code}"
        )


def audit_configuration(
    *,
    load_balancers: list[dict[str, Any]],
    pools: list[dict[str, Any]],
    monitors: list[dict[str, Any]],
    config: AuditConfig,
) -> list[str]:
    messages: list[str] = []
    lb = _find_lb(load_balancers, config.hostname)
    lb_name = _name(lb)
    if not bool(lb.get("enabled", True)):
        raise AuditFailure(f"load balancer {lb_name!r} is disabled")
    messages.append(f"load_balancer={lb_name} enabled=true")

    default_pools = [str(pool_id) for pool_id in (lb.get("default_pools") or [])]
    if len(default_pools) < 2:
        raise AuditFailure(f"load balancer {lb_name!r} has fewer than two default_pools")

    primary_pool = _find_pool_by_origin(pools, config.primary_origin)
    standby_pool = _find_pool_by_origin(pools, config.standby_origin)
    primary_pool_id = _id(primary_pool)
    standby_pool_id = _id(standby_pool)
    expected_prefix = [primary_pool_id, standby_pool_id]
    if default_pools[:2] != expected_prefix:
        raise AuditFailure(
            f"default_pools first two must be primary then standby. "
            f"expected={expected_prefix}, actual={default_pools[:2]}"
        )
    if not config.allow_extra_default_pools and len(default_pools) != 2:
        raise AuditFailure(f"default_pools has extra pools: {default_pools}")
    messages.append(
        f"default_pools_order=primary({_name(primary_pool)}) -> standby({_name(standby_pool)})"
    )

    fallback_pool = str(lb.get("fallback_pool") or "")
    if fallback_pool != primary_pool_id:
        raise AuditFailure(
            f"fallback_pool must be primary pool {_name(primary_pool)!r}; "
            f"got {fallback_pool or '<empty>'}"
        )
    messages.append(f"fallback_pool=primary({_name(primary_pool)})")

    if config.require_adaptive_failover:
        adaptive = lb.get("adaptive_routing") or {}
        if not isinstance(adaptive, dict) or adaptive.get("failover_across_pools") is not True:
            raise AuditFailure("adaptive_routing.failover_across_pools must be true")
        messages.append("adaptive_routing.failover_across_pools=true")

    if config.require_session_affinity_off:
        affinity = str(lb.get("session_affinity") or "none").lower()
        if affinity not in {"", "none"}:
            raise AuditFailure(f"session_affinity must be off/none, got {affinity!r}")
        messages.append("session_affinity=none")

    monitor_map = _monitor_by_id(monitors)
    for pool, address, role in (
        (primary_pool, config.primary_origin, "primary"),
        (standby_pool, config.standby_origin, "standby"),
    ):
        if not bool(pool.get("enabled", True)):
            raise AuditFailure(f"{role} pool {_name(pool)!r} is disabled")
        _check_origin(pool, address, config.host_header)
        _check_pool_monitor(pool, monitor_map, config)
        messages.append(f"{role}_pool={_name(pool)} origin={address} monitor=ok")

    return messages


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Cloudflare Load Balancer config for MVN API HA.")
    parser.add_argument("--hostname", default=os.getenv("CF_LB_HOSTNAME", "api.mvn.by"))
    parser.add_argument("--primary-origin", default=os.getenv("CF_LB_PRIMARY_ORIGIN", "185.250.45.54"))
    parser.add_argument("--standby-origin", default=os.getenv("CF_LB_STANDBY_ORIGIN", "193.47.42.213"))
    parser.add_argument("--host-header", default=os.getenv("CF_LB_HOST_HEADER", "api.mvn.by"))
    parser.add_argument("--monitor-path", default=os.getenv("CF_LB_MONITOR_PATH", "/api/ready"))
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
    parser.add_argument(
        "--skip-if-missing-credentials",
        action="store_true",
        default=_normalize_bool(os.getenv("CF_LB_SKIP_IF_MISSING_CREDENTIALS"), default=False),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID", "").strip()
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
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
        message = "missing Cloudflare credentials: " + ", ".join(missing)
        if args.skip_if_missing_credentials:
            _log("skip", message)
            return 0
        raise SystemExit(message)

    config = AuditConfig(
        hostname=args.hostname,
        primary_origin=args.primary_origin,
        standby_origin=args.standby_origin,
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
        messages = audit_configuration(
            load_balancers=load_balancers,
            pools=pools,
            monitors=monitors,
            config=config,
        )
    except AuditFailure as exc:
        _log("fail", str(exc))
        return 1

    for message in messages:
        _log("ok", message)
    _log("summary", "status=passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
