#!/usr/bin/env python3
"""Strict, role-aware proof of the reviewed two-node Patroni topology."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

try:
    from scripts.ha.pitr_pinned_ssh import (
        PATRONI_NODES,
        PatroniNode,
        PinnedSshContext,
        ssh_args,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PATRONI_NODES,
        PatroniNode,
        PinnedSshContext,
        ssh_args,
    )


Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]
EXPECTED_SCOPE = "mvn-postgres"
MAX_REPLAY_LAG_BYTES = 1_048_576
PRIMARY_ROLES = {"leader", "master", "primary"}
STANDBY_ROLES = {"replica", "standby", "sync_standby", "synchronous_standby"}
WIREGUARD_ADDRESSES = {"mvn-api": "10.77.0.2", "zakup": "10.77.0.1"}


@dataclass(frozen=True)
class ClusterTopology:
    primary: PatroniNode
    standby: PatroniNode
    system_identifier: str
    timeline: int


def _clean(value: object | None) -> str:
    return str(value or "").strip()


def _run(
    node: PatroniNode,
    context: PinnedSshContext,
    command: str,
    *,
    runner: Runner,
    stdin: str | None = None,
) -> str:
    result = runner([*ssh_args(node, context), command], stdin)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "remote probe failed").strip()
        raise RuntimeError(f"{node.alias}: {detail}")
    return result.stdout.strip()


def _endpoint_json(
    node: PatroniNode,
    context: PinnedSshContext,
    endpoint: str,
    *,
    runner: Runner,
) -> Mapping[str, object]:
    if endpoint not in {"patroni", "cluster"}:
        raise RuntimeError("unreviewed Patroni JSON endpoint")
    raw = _run(
        node,
        context,
        f"curl -fsS --max-time 5 http://127.0.0.1:8008/{endpoint}",
        runner=runner,
    )
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(f"{node.alias}: invalid Patroni /{endpoint} JSON") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"{node.alias}: invalid Patroni /{endpoint} payload")
    return payload


def _patroni_role(payload: Mapping[str, object], node: PatroniNode) -> str:
    nested = payload.get("patroni")
    nested_name = nested.get("name") if isinstance(nested, Mapping) else ""
    scope = _clean(nested.get("scope") if isinstance(nested, Mapping) else "")
    name = _clean(payload.get("name") or nested_name)
    if _clean(payload.get("state")).lower() != "running":
        raise RuntimeError(f"{node.alias}: Patroni is not running")
    if name != node.alias:
        raise RuntimeError(
            f"{node.alias}: Patroni identity is {name or '<empty>'}, expected {node.alias}"
        )
    if scope != EXPECTED_SCOPE:
        raise RuntimeError(
            f"{node.alias}: Patroni scope is {scope or '<empty>'}, expected {EXPECTED_SCOPE}"
        )
    unsafe = {
        "pending_restart": "pending restart",
        "pause": "cluster pause",
        "cluster_unlocked": "missing DCS leader lock",
        "failsafe_mode_is_active": "DCS failsafe mode",
    }
    for field, description in unsafe.items():
        value = payload.get(field, False)
        if type(value) is not bool:
            raise RuntimeError(f"{node.alias}: Patroni {field} state is invalid")
        if value:
            raise RuntimeError(f"{node.alias}: Patroni reports {description}")
    role = _clean(payload.get("role")).lower()
    if role in PRIMARY_ROLES:
        return "primary"
    if role in STANDBY_ROLES:
        return "standby"
    raise RuntimeError(f"{node.alias}: unsupported Patroni role: {role or '<empty>'}")


def _cluster_view(
    payload: Mapping[str, object],
    *,
    source: PatroniNode,
    primary: PatroniNode,
    standby: PatroniNode,
) -> tuple[tuple[object, ...], tuple[object, ...], int]:
    raw_members = payload.get("members")
    if not isinstance(raw_members, list) or len(raw_members) != 2:
        raise RuntimeError(f"{source.alias}: /cluster has no member list")
    if any(not isinstance(item, Mapping) for item in raw_members):
        raise RuntimeError(f"{source.alias}: /cluster member entry is invalid")
    member_names = [_clean(item.get("name")) for item in raw_members]
    if any(not name for name in member_names) or len(set(member_names)) != 2:
        raise RuntimeError(f"{source.alias}: /cluster member identities are invalid")
    members = {name: item for name, item in zip(member_names, raw_members)}
    if set(members) != {primary.alias, standby.alias}:
        raise RuntimeError(f"{source.alias}: /cluster member set is not reviewed")
    leader = members[primary.alias]
    replica = members[standby.alias]
    if _clean(leader.get("role")).lower() not in PRIMARY_ROLES:
        raise RuntimeError(f"{source.alias}: /cluster leader role is invalid")
    if _clean(replica.get("role")).lower() not in STANDBY_ROLES:
        raise RuntimeError(f"{source.alias}: /cluster standby role is invalid")
    if _clean(leader.get("state")).lower() != "running":
        raise RuntimeError(f"{source.alias}: /cluster leader is not running")
    if _clean(replica.get("state")).lower() not in {"running", "streaming"}:
        raise RuntimeError(f"{source.alias}: /cluster standby is not streaming")
    pending_values = (
        leader.get("pending_restart", False),
        replica.get("pending_restart", False),
    )
    if any(type(value) is not bool for value in pending_values):
        raise RuntimeError(f"{source.alias}: /cluster pending restart state is invalid")
    if any(pending_values):
        raise RuntimeError(f"{source.alias}: /cluster member has pending restart")
    lag_value = replica.get("lag", 0)
    if type(lag_value) is not int:
        raise RuntimeError(f"{source.alias}: /cluster lag is invalid")
    try:
        lag = int(lag_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{source.alias}: /cluster lag is invalid") from exc
    if lag < 0 or lag > MAX_REPLAY_LAG_BYTES:
        raise RuntimeError(f"{source.alias}: /cluster lag exceeds the reviewed bound")
    timelines = {leader.get("timeline"), replica.get("timeline")}
    if len(timelines) != 1:
        raise RuntimeError(f"{source.alias}: /cluster timelines disagree")
    timeline = next(iter(timelines))
    if type(timeline) is not int or timeline <= 0:
        raise RuntimeError(f"{source.alias}: /cluster timeline is invalid")

    def canonical(member: Mapping[str, object]) -> tuple[object, ...]:
        return (
            _clean(member.get("name")),
            _clean(member.get("role")).lower(),
            _clean(member.get("state")).lower(),
            member.get("timeline"),
            bool(member.get("pending_restart")),
        )

    return canonical(leader), canonical(replica), timeline


def _sql(
    node: PatroniNode,
    context: PinnedSshContext,
    statement: str,
    *,
    runner: Runner,
) -> str:
    compose = shlex.join(["docker", "compose", "-f", node.compose_file])
    psql = (
        'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" '
        '-d "${POSTGRES_DB:-air_conditioners}" -AtF "|"'
    )
    command = (
        f"cd {shlex.quote(node.project_dir)} && {compose} exec -T db "
        f"sh -lc {shlex.quote(psql)}"
    )
    return _run(node, context, command, runner=runner, stdin=statement)


def _rows(raw: str, columns: int) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("|")
        if len(parts) != columns:
            raise RuntimeError("PostgreSQL topology probe returned an invalid row")
        rows.append(parts)
    return rows


def _validate_postgres(
    primary: PatroniNode,
    standby: PatroniNode,
    context: PinnedSshContext,
    *,
    runner: Runner,
) -> str:
    if _sql(primary, context, "select pg_is_in_recovery();", runner=runner) != "f":
        raise RuntimeError(f"{primary.alias}: PostgreSQL is not writable primary")
    if _sql(standby, context, "select pg_is_in_recovery();", runner=runner) != "t":
        raise RuntimeError(f"{standby.alias}: PostgreSQL is not in recovery")
    system_sql = "select system_identifier from pg_control_system();"
    primary_system = _sql(primary, context, system_sql, runner=runner)
    standby_system = _sql(standby, context, system_sql, runner=runner)
    if (
        not re.fullmatch(r"[0-9]{10,24}", primary_system)
        or primary_system != standby_system
    ):
        raise RuntimeError("PostgreSQL system identifiers do not match")
    replication_sql = """
select coalesce(application_name, ''), coalesce(host(client_addr), ''),
       coalesce(state, ''), coalesce(sync_state, ''),
       coalesce(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint, -1)
from pg_stat_replication order by application_name;
"""
    rows = _rows(_sql(primary, context, replication_sql, runner=runner), 5)
    matching = [row for row in rows if row[0] == standby.alias]
    if len(matching) != 1:
        raise RuntimeError(f"{primary.alias}: expected one reviewed replication row")
    _, address, state, sync_state, lag_raw = matching[0]
    try:
        lag = int(lag_raw)
    except ValueError as exc:
        raise RuntimeError(f"{primary.alias}: replication lag is invalid") from exc
    if (
        address != WIREGUARD_ADDRESSES[standby.alias]
        or state != "streaming"
        or sync_state != "sync"
        or lag < 0
        or lag > MAX_REPLAY_LAG_BYTES
    ):
        raise RuntimeError(f"{primary.alias}: synchronous replication is not healthy")
    receiver_sql = """
select coalesce(status, ''), coalesce(sender_host, ''), coalesce(slot_name, ''),
       coalesce(pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn())::bigint, 0)
from pg_stat_wal_receiver;
"""
    receivers = _rows(_sql(standby, context, receiver_sql, runner=runner), 4)
    if len(receivers) != 1:
        raise RuntimeError(f"{standby.alias}: expected one WAL receiver")
    status, sender, slot, receiver_lag_raw = receivers[0]
    try:
        receiver_lag = max(0, int(receiver_lag_raw))
    except ValueError as exc:
        raise RuntimeError(f"{standby.alias}: WAL receiver lag is invalid") from exc
    if (
        status != "streaming"
        or sender != WIREGUARD_ADDRESSES[primary.alias]
        or not slot
        or receiver_lag > MAX_REPLAY_LAG_BYTES
    ):
        raise RuntimeError(f"{standby.alias}: WAL receiver is not healthy")
    sync_names = _sql(primary, context, "show synchronous_standby_names;", runner=runner)
    if standby.alias not in sync_names:
        raise RuntimeError("synchronous_standby_names does not name the reviewed standby")
    return primary_system


def discover_cluster_topology(
    *,
    context: PinnedSshContext,
    runner: Runner,
    nodes: Sequence[PatroniNode] = PATRONI_NODES,
) -> ClusterTopology:
    if len(nodes) != 2 or {node.alias for node in nodes} != set(WIREGUARD_ADDRESSES):
        raise RuntimeError("PITR topology requires the two reviewed Patroni nodes")
    patroni_payloads = {
        node.alias: _endpoint_json(node, context, "patroni", runner=runner)
        for node in nodes
    }
    roles = {
        node.alias: _patroni_role(patroni_payloads[node.alias], node) for node in nodes
    }
    primaries = [node for node in nodes if roles[node.alias] == "primary"]
    standbys = [node for node in nodes if roles[node.alias] == "standby"]
    if len(primaries) != 1 or len(standbys) != 1:
        rendered = " ".join(f"{name}={roles[name]}" for name in sorted(roles))
        raise RuntimeError(f"unsafe Patroni topology: {rendered}")
    primary, standby = primaries[0], standbys[0]
    views = [
        _cluster_view(
            _endpoint_json(node, context, "cluster", runner=runner),
            source=node,
            primary=primary,
            standby=standby,
        )
        for node in nodes
    ]
    if views[0] != views[1]:
        raise RuntimeError("Patroni nodes disagree on the DCS cluster view")
    _run(
        primary,
        context,
        "curl -fsS --max-time 5 http://127.0.0.1:8008/leader >/dev/null",
        runner=runner,
    )
    _run(
        standby,
        context,
        "curl -fsS --max-time 5 http://127.0.0.1:8008/sync >/dev/null",
        runner=runner,
    )
    system_identifier = _validate_postgres(
        primary, standby, context, runner=runner
    )
    return ClusterTopology(
        primary=primary,
        standby=standby,
        system_identifier=system_identifier,
        timeline=views[0][2],
    )
