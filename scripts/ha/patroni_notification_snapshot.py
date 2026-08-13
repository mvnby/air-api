"""Build secret-free owner-notification snapshots from a proven Patroni check."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


ClusterLoader = Callable[[Any, Any, str], Mapping[str, Any]]
ReadyLoader = Callable[[Any, Any, str], tuple[int, Mapping[str, Any]]]


def build_notification_snapshot(
    config: Any,
    runner: Any,
    report: Any,
    primary: Any,
    standby: Any,
    *,
    cluster_loader: ClusterLoader,
    ready_loader: ReadyLoader,
) -> dict[str, object]:
    cluster = cluster_loader(runner, primary, "cluster")
    members = cluster.get("members")
    if not isinstance(members, list):
        raise RuntimeError("Patroni /cluster has no member list")
    replica = next(
        (
            item
            for item in members
            if isinstance(item, Mapping) and item.get("name") == standby.patroni_name
        ),
        None,
    )
    if not isinstance(replica, Mapping):
        raise RuntimeError("Patroni /cluster has no standby member")
    lag_raw = replica.get("lag", 0)
    if type(lag_raw) is not int:
        raise RuntimeError("Patroni /cluster lag is not an integer")

    primary_code, primary_body = ready_loader(runner, primary, config.ready_url)
    standby_code, standby_body = ready_loader(runner, standby, config.ready_url)
    primary_ready = (
        primary_code == 200
        and primary_body.get("api") == "ready"
        and primary_body.get("traffic") == "enabled"
    )
    standby_fenced = (
        standby_code == 503
        and standby_body.get("api") == "not_ready"
        and standby_body.get("traffic") == "disabled"
    )

    if not primary_ready:
        status = "critical"
    elif report.failures:
        status = "degraded"
    else:
        status = "healthy"
    return {
        "status": status,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "primary": primary.patroni_name,
        "standby": standby.patroni_name,
        "timeline": next(
            (
                item.get("timeline")
                for item in members
                if isinstance(item, Mapping) and item.get("name") == primary.patroni_name
            ),
            None,
        ),
        "lag_bytes": lag_raw,
        "primary_ready": primary_ready,
        "standby_fenced": standby_fenced,
        "replication_state": str(replica.get("state") or ""),
        "sync_state": str(replica.get("role") or ""),
        "failures": list(report.failures),
        "detail": "",
    }


def failure_snapshot(error: Exception) -> dict[str, object]:
    detail = str(error).strip().replace("\n", " ")[:500]
    unsafe_topology = any(
        marker in detail.lower()
        for marker in (
            "unsafe patroni topology",
            "failsafe mode is active",
            "pending_restart",
        )
    )
    return {
        "status": "critical" if unsafe_topology else "monitoring_error",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "primary": "",
        "standby": "",
        "timeline": None,
        "lag_bytes": None,
        "primary_ready": None,
        "standby_fenced": None,
        "replication_state": "",
        "sync_state": "",
        "failures": [detail] if unsafe_topology else [],
        "detail": detail,
    }


def write_snapshot(path: Path | None, snapshot: Mapping[str, object]) -> None:
    if path is None:
        return
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
