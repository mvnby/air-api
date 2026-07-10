#!/usr/bin/env python3
"""Verify the live two-node MVN Patroni cluster through SSH.

The checker is role-aware: the API VPS and reserve VPS are node identities,
not permanent PostgreSQL roles. It verifies DCS topology, PostgreSQL streaming
and synchronous durability, API fencing, singleton bot/PITR ownership, and the
three-member etcd quorum without reading database or infrastructure secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


PRIMARY_ROLES = {"leader", "master", "primary"}
REPLICA_ROLES = {"replica", "standby"}
CLUSTER_PRIMARY_ROLES = PRIMARY_ROLES
CLUSTER_REPLICA_ROLES = {
    "replica",
    "standby",
    "sync_standby",
    "synchronous_standby",
}
PITR_TIMERS = (
    "mvn-postgres-wal-upload.timer",
    "mvn-postgres-basebackup.timer",
)


@dataclass(frozen=True)
class NodeConfig:
    label: str
    patroni_name: str
    ssh_target: str
    project_dir: str
    compose_file: str
    wireguard_ip: str


@dataclass(frozen=True)
class CheckerConfig:
    api: NodeConfig
    reserve: NodeConfig
    ssh_options: tuple[str, ...]
    max_replay_lag_bytes: int
    role_agent_unit: str
    etcd_check_command: str
    ready_url: str

    @property
    def nodes(self) -> tuple[NodeConfig, NodeConfig]:
        return (self.api, self.reserve)


@dataclass
class Report:
    ok: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def pass_check(self, message: str) -> None:
        self.ok.append(message)

    def fail(self, message: str) -> None:
        self.failures.append(message)


class SshRunner:
    def __init__(self, options: Sequence[str]) -> None:
        self.options = tuple(options)

    def run(
        self,
        node: NodeConfig,
        command: str,
        *,
        stdin: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["ssh", *self.options, node.ssh_target, command],
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout or "remote command failed").strip()
            raise RuntimeError(f"{node.label}: {detail}")
        return result


def _required_env(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _unsigned_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an unsigned integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be an unsigned integer")
    return value


def load_config() -> CheckerConfig:
    ssh_options = tuple(
        shlex.split(
            os.getenv(
                "SSH_OPTS",
                "-o BatchMode=yes -o StrictHostKeyChecking=yes "
                "-o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=3",
            )
        )
    )
    return CheckerConfig(
        api=NodeConfig(
            label="api",
            patroni_name=os.getenv("API_NODE_PATRONI_NAME", "mvn-api").strip(),
            ssh_target=_required_env("API_NODE_SSH", "mvn-api"),
            project_dir=_required_env("API_NODE_PROJECT_DIR", "/opt/air-api"),
            compose_file=_required_env("API_NODE_COMPOSE_FILE", "docker-compose.patroni.yml"),
            wireguard_ip=_required_env("API_NODE_WG_IP", "10.77.0.2"),
        ),
        reserve=NodeConfig(
            label="reserve",
            patroni_name=os.getenv("RESERVE_NODE_PATRONI_NAME", "zakup").strip(),
            ssh_target=_required_env("RESERVE_NODE_SSH", "zakup"),
            project_dir=_required_env("RESERVE_NODE_PROJECT_DIR", "/opt/mvn-reserve"),
            compose_file=_required_env(
                "RESERVE_NODE_COMPOSE_FILE", "docker-compose.patroni.yml"
            ),
            wireguard_ip=_required_env("RESERVE_NODE_WG_IP", "10.77.0.1"),
        ),
        ssh_options=ssh_options,
        max_replay_lag_bytes=_unsigned_int("MAX_REPLAY_LAG_BYTES", 1_048_576),
        role_agent_unit=os.getenv(
            "PATRONI_ROLE_AGENT_UNIT", "mvn-patroni-role-agent.service"
        ).strip(),
        etcd_check_command=os.getenv(
            "ETCD_CHECK_COMMAND", "bash /opt/mvn-quorum/check_etcd_quorum.sh"
        ).strip(),
        ready_url=os.getenv(
            "PATRONI_READY_URL", "http://127.0.0.1:18080/api/ready"
        ).strip(),
    )


def role_from_patroni(payload: Mapping[str, Any]) -> str:
    state = str(payload.get("state") or "").strip().lower()
    role = str(payload.get("role") or "").strip().lower()
    if state != "running":
        raise ValueError(f"Patroni state is {state or '<empty>'}, expected running")
    if role in PRIMARY_ROLES:
        return "primary"
    if role in REPLICA_ROLES:
        return "standby"
    raise ValueError(f"unsupported Patroni role: {role or '<empty>'}")


def select_primary(
    nodes: Sequence[NodeConfig], payloads: Mapping[str, Mapping[str, Any]]
) -> tuple[NodeConfig, NodeConfig]:
    roles: dict[str, str] = {}
    for node in nodes:
        payload = payloads[node.label]
        patroni_metadata = payload.get("patroni")
        nested_name = (
            patroni_metadata.get("name") if isinstance(patroni_metadata, Mapping) else ""
        )
        actual_name = str(payload.get("name") or nested_name or "").strip()
        if actual_name != node.patroni_name:
            raise ValueError(
                f"{node.label}: Patroni name is {actual_name or '<empty>'}, "
                f"expected {node.patroni_name}"
            )
        if payload.get("pending_restart") is True:
            raise ValueError(f"{node.label}: Patroni reports pending_restart")
        if payload.get("pause") is True:
            raise ValueError(f"{node.label}: Patroni cluster is paused")
        if payload.get("cluster_unlocked") is True:
            raise ValueError(f"{node.label}: Patroni cluster has no leader lock")
        if payload.get("failsafe_mode_is_active") is True:
            raise ValueError(f"{node.label}: Patroni DCS failsafe mode is active")
        roles[node.label] = role_from_patroni(payload)

    primaries = [node for node in nodes if roles[node.label] == "primary"]
    standbys = [node for node in nodes if roles[node.label] == "standby"]
    if len(primaries) != 1 or len(standbys) != 1:
        rendered = " ".join(f"{label}={role}" for label, role in sorted(roles.items()))
        raise ValueError(f"unsafe Patroni topology: {rendered}")
    return primaries[0], standbys[0]


def _json_remote(runner: SshRunner, node: NodeConfig, path: str) -> dict[str, Any]:
    result = runner.run(
        node,
        f"curl -fsS --max-time 5 http://127.0.0.1:8008/{shlex.quote(path)}",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{node.label}: invalid Patroni JSON from /{path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{node.label}: unexpected Patroni payload from /{path}")
    return payload


def probe_nodes(
    config: CheckerConfig, runner: SshRunner
) -> dict[str, dict[str, Any]]:
    return {node.label: _json_remote(runner, node, "patroni") for node in config.nodes}


def _compose_prefix(node: NodeConfig, *, profiles: bool = False) -> str:
    command = ["docker", "compose", "-f", node.compose_file]
    if profiles:
        command.extend(["--profile", "bluegreen"])
    return f"cd {shlex.quote(node.project_dir)} && {shlex.join(command)}"


def _sql(runner: SshRunner, node: NodeConfig, statement: str) -> str:
    psql = (
        'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" '
        '-d "${POSTGRES_DB:-air_conditioners}" -AtF "|"'
    )
    command = (
        f"{_compose_prefix(node)} exec -T db sh -lc {shlex.quote(psql)}"
    )
    return runner.run(node, command, stdin=statement).stdout.strip()


def _check_cluster_views(
    config: CheckerConfig,
    runner: SshRunner,
    primary: NodeConfig,
    standby: NodeConfig,
    report: Report,
) -> None:
    initial_failure_count = len(report.failures)
    expected_names = {node.patroni_name for node in config.nodes}
    for source in config.nodes:
        payload = _json_remote(runner, source, "cluster")
        raw_members = payload.get("members")
        if not isinstance(raw_members, list):
            report.fail(f"{source.label}: /cluster has no member list")
            continue
        members = {
            str(member.get("name") or ""): member
            for member in raw_members
            if isinstance(member, dict)
        }
        if set(members) != expected_names:
            report.fail(
                f"{source.label}: DCS members={sorted(members)} expected={sorted(expected_names)}"
            )
            continue

        leader = members[primary.patroni_name]
        replica = members[standby.patroni_name]
        leader_role = str(leader.get("role") or "").lower()
        replica_role = str(replica.get("role") or "").lower()
        if leader_role not in CLUSTER_PRIMARY_ROLES:
            report.fail(
                f"{source.label}: DCS leader role={leader_role or '<empty>'}"
            )
        if replica_role not in CLUSTER_REPLICA_ROLES:
            report.fail(
                f"{source.label}: replica role={replica_role or '<empty>'}"
            )
        if str(leader.get("state") or "").lower() != "running":
            report.fail(f"{source.label}: DCS leader is not running")
        if str(replica.get("state") or "").lower() not in {"running", "streaming"}:
            report.fail(f"{source.label}: DCS replica is not streaming")
        if leader.get("pending_restart") is True or replica.get("pending_restart") is True:
            report.fail(f"{source.label}: DCS member has pending_restart")

        lag = replica.get("lag")
        try:
            lag_bytes = int(lag or 0)
        except (TypeError, ValueError):
            report.fail(f"{source.label}: replica lag is not numeric: {lag!r}")
        else:
            if lag_bytes > config.max_replay_lag_bytes:
                report.fail(
                    f"{source.label}: DCS lag {lag_bytes} exceeds "
                    f"{config.max_replay_lag_bytes} bytes"
                )

        timelines = {member.get("timeline") for member in (leader, replica)}
        timelines.discard(None)
        if len(timelines) > 1:
            report.fail(f"{source.label}: members disagree on timeline: {sorted(timelines)}")

    sync_probe = runner.run(
        standby,
        "curl -fsS --max-time 5 http://127.0.0.1:8008/sync >/dev/null",
        check=False,
    )
    if sync_probe.returncode != 0:
        report.fail(f"{standby.label}: Patroni /sync endpoint is not healthy")

    if len(report.failures) == initial_failure_count:
        report.pass_check(
            f"DCS topology has leader={primary.patroni_name} "
            f"sync_standby={standby.patroni_name}"
        )


def _parse_rows(value: str, columns: int) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in value.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) != columns:
            raise ValueError(f"unexpected SQL row: {line!r}")
        rows.append(parts)
    return rows


def _check_postgres(
    config: CheckerConfig,
    runner: SshRunner,
    primary: NodeConfig,
    standby: NodeConfig,
    report: Report,
) -> None:
    initial_failure_count = len(report.failures)
    primary_recovery = _sql(runner, primary, "select pg_is_in_recovery();")
    standby_recovery = _sql(runner, standby, "select pg_is_in_recovery();")
    if primary_recovery != "f":
        report.fail(f"{primary.label}: PostgreSQL is not writable primary")
    if standby_recovery != "t":
        report.fail(f"{standby.label}: PostgreSQL is not in recovery")

    system_id_sql = "select system_identifier from pg_control_system();"
    primary_system_id = _sql(runner, primary, system_id_sql)
    standby_system_id = _sql(runner, standby, system_id_sql)
    if not primary_system_id or primary_system_id != standby_system_id:
        report.fail(
            f"PostgreSQL system identifiers differ: primary={primary_system_id or '<empty>'} "
            f"standby={standby_system_id or '<empty>'}"
        )

    replication_sql = """
select
  coalesce(application_name, ''),
  coalesce(client_addr::text, ''),
  coalesce(state, ''),
  coalesce(sync_state, ''),
  coalesce(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint, -1)
from pg_stat_replication
order by application_name;
"""
    rows = _parse_rows(_sql(runner, primary, replication_sql), 5)
    matching = [row for row in rows if row[0] == standby.patroni_name]
    if len(matching) != 1:
        report.fail(
            f"{primary.label}: expected one replication row for {standby.patroni_name}, "
            f"got {len(matching)}"
        )
    else:
        application, client_addr, state, sync_state, lag_raw = matching[0]
        if client_addr != standby.wireguard_ip:
            report.fail(
                f"{primary.label}: replica address={client_addr or '<empty>'}, "
                f"expected {standby.wireguard_ip}"
            )
        if state != "streaming":
            report.fail(f"{primary.label}: replication state={state or '<empty>'}")
        if sync_state != "sync":
            report.fail(f"{primary.label}: sync_state={sync_state or '<empty>'}")
        try:
            replay_lag = int(lag_raw)
        except ValueError:
            report.fail(f"{primary.label}: replay lag is not numeric: {lag_raw!r}")
        else:
            if replay_lag < 0 or replay_lag > config.max_replay_lag_bytes:
                report.fail(
                    f"{primary.label}: replay lag {replay_lag} exceeds "
                    f"{config.max_replay_lag_bytes} bytes"
                )

    receiver_sql = """
select
  coalesce(status, ''),
  coalesce(sender_host, ''),
  coalesce(slot_name, ''),
  coalesce(pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn())::bigint, 0)
from pg_stat_wal_receiver;
"""
    receiver_rows = _parse_rows(_sql(runner, standby, receiver_sql), 4)
    if len(receiver_rows) != 1:
        report.fail(f"{standby.label}: expected one WAL receiver, got {len(receiver_rows)}")
    else:
        status, sender_host, slot_name, receive_replay_lag_raw = receiver_rows[0]
        if status != "streaming":
            report.fail(f"{standby.label}: WAL receiver status={status or '<empty>'}")
        if sender_host != primary.wireguard_ip:
            report.fail(
                f"{standby.label}: WAL sender={sender_host or '<empty>'}, "
                f"expected {primary.wireguard_ip}"
            )
        if not slot_name:
            report.fail(f"{standby.label}: WAL receiver has no replication slot")
        try:
            receive_replay_lag = int(receive_replay_lag_raw)
        except ValueError:
            report.fail(
                f"{standby.label}: receive/replay lag is not numeric: {receive_replay_lag_raw!r}"
            )
        else:
            if receive_replay_lag < 0 or receive_replay_lag > config.max_replay_lag_bytes:
                report.fail(
                    f"{standby.label}: receive/replay lag {receive_replay_lag} exceeds "
                    f"{config.max_replay_lag_bytes} bytes"
                )

    sync_names = _sql(runner, primary, "show synchronous_standby_names;")
    if standby.patroni_name not in sync_names:
        report.fail(
            f"{primary.label}: synchronous_standby_names does not include "
            f"{standby.patroni_name}"
        )
    if _sql(runner, primary, "show wal_log_hints;").lower() != "on":
        report.fail(f"{primary.label}: wal_log_hints is not on")
    if _sql(runner, primary, "show archive_mode;").lower() != "on":
        report.fail(f"{primary.label}: archive_mode is not on")

    if len(report.failures) == initial_failure_count:
        report.pass_check(
            f"PostgreSQL primary={primary.patroni_name} streams synchronously to "
            f"{standby.patroni_name} with matching system identifier"
        )


def _unit_active(runner: SshRunner, node: NodeConfig, unit: str) -> bool:
    return (
        runner.run(
            node,
            f"systemctl is-active --quiet {shlex.quote(unit)}",
            check=False,
        ).returncode
        == 0
    )


def _unit_enabled(runner: SshRunner, node: NodeConfig, unit: str) -> bool:
    return (
        runner.run(
            node,
            f"systemctl is-enabled --quiet {shlex.quote(unit)}",
            check=False,
        ).returncode
        == 0
    )


def _ready_response(
    runner: SshRunner, node: NodeConfig, ready_url: str
) -> tuple[int, dict[str, Any]]:
    command = f"curl -sS --max-time 5 -w '\\n%{{http_code}}' {shlex.quote(ready_url)}"
    result = runner.run(node, command)
    lines = result.stdout.rstrip().splitlines()
    if len(lines) < 2:
        raise RuntimeError(f"{node.label}: invalid readiness response")
    try:
        status = int(lines[-1])
        payload = json.loads("\n".join(lines[:-1]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{node.label}: invalid readiness response") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{node.label}: readiness payload is not an object")
    return status, payload


def _running_services(runner: SshRunner, node: NodeConfig) -> set[str]:
    command = f"{_compose_prefix(node, profiles=True)} ps --status running --services"
    return set(runner.run(node, command).stdout.split())


def _role_env(runner: SshRunner, node: NodeConfig, filename: str) -> dict[str, str]:
    path = f"{node.project_dir}/{filename}"
    content = runner.run(node, f"cat {shlex.quote(path)}").stdout
    values: dict[str, str] = {}
    for line in content.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip()
    return values


def _check_runtime(
    config: CheckerConfig,
    runner: SshRunner,
    primary: NodeConfig,
    standby: NodeConfig,
    report: Report,
) -> None:
    initial_failure_count = len(report.failures)
    for node in config.nodes:
        expected_role = "primary" if node == primary else "standby"
        if not _unit_enabled(runner, node, config.role_agent_unit):
            report.fail(f"{node.label}: Patroni role agent is not enabled")
        if not _unit_active(runner, node, config.role_agent_unit):
            report.fail(f"{node.label}: Patroni role agent is not active")

        role_state = runner.run(
            node,
            f"cat {shlex.quote(node.project_dir + '/.ha-runtime-role')}",
        ).stdout.strip()
        if role_state != expected_role:
            report.fail(
                f"{node.label}: runtime role={role_state or '<empty>'}, expected {expected_role}"
            )

        app_env = _role_env(runner, node, ".ha-app-role.env")
        bot_env = _role_env(runner, node, ".ha-bot-role.env")
        expected_primary = node == primary
        expected_app_values = {
            "APP_ROLE": expected_role,
            "API_READY_ENABLED": str(expected_primary).lower(),
            "DB_BOOTSTRAP_ENABLED": "false",
            "SCHEDULER_ENABLED": str(expected_primary).lower(),
        }
        expected_bot_values = {
            "APP_ROLE": expected_role,
            "API_READY_ENABLED": "false",
            "BOT_ENABLED": str(expected_primary).lower(),
            "DB_BOOTSTRAP_ENABLED": "false",
            "SCHEDULER_ENABLED": "false",
        }
        for name, expected in expected_app_values.items():
            if app_env.get(name) != expected:
                report.fail(
                    f"{node.label}: app role env {name}={app_env.get(name)!r}, expected {expected!r}"
                )
        for name, expected in expected_bot_values.items():
            if bot_env.get(name) != expected:
                report.fail(
                    f"{node.label}: bot role env {name}={bot_env.get(name)!r}, expected {expected!r}"
                )
        if not expected_primary:
            for name in (
                "MAIL_IMAP_AUTO_IMPORT_ENABLED",
                "MAIL_IMAP_LEAD_AUTO_IMPORT_ENABLED",
                "CLOUDFLARE_PURGE_ENABLED",
            ):
                if app_env.get(name) != "false":
                    report.fail(
                        f"{node.label}: standby app role env {name} is not false"
                    )

        services = _running_services(runner, node)
        app_services = services.intersection({"app", "app-blue", "app-green"})
        if not app_services:
            report.fail(f"{node.label}: no API app service is running")
        bot_running = "bot" in services
        if bot_running != (node == primary):
            report.fail(
                f"{node.label}: bot_running={str(bot_running).lower()} expected="
                f"{str(node == primary).lower()}"
            )

        status, payload = _ready_response(runner, node, config.ready_url)
        if node == primary:
            if status != 200 or payload.get("api") != "ready" or payload.get("traffic") != "enabled":
                report.fail(
                    f"{node.label}: primary readiness is HTTP {status} "
                    f"api={payload.get('api')} traffic={payload.get('traffic')}"
                )
        elif status != 503 or payload.get("api") != "not_ready" or payload.get("traffic") != "disabled":
            report.fail(
                f"{node.label}: standby fencing is HTTP {status} "
                f"api={payload.get('api')} traffic={payload.get('traffic')}"
            )

        for timer in PITR_TIMERS:
            active = _unit_active(runner, node, timer)
            if active != (node == primary):
                report.fail(
                    f"{node.label}: {timer} active={str(active).lower()} "
                    f"expected={str(node == primary).lower()}"
                )

    if len(report.failures) == initial_failure_count:
        report.pass_check(
            f"runtime ownership follows primary={primary.label}: one bot, one ready API, PITR timers fenced"
        )


def perform_checks(config: CheckerConfig, runner: SshRunner) -> Report:
    report = Report()
    payloads = probe_nodes(config, runner)
    primary, standby = select_primary(config.nodes, payloads)
    report.pass_check(
        f"exactly one Patroni primary: {primary.label} ({primary.patroni_name})"
    )

    _check_cluster_views(config, runner, primary, standby, report)
    _check_postgres(config, runner, primary, standby, report)
    _check_runtime(config, runner, primary, standby, report)

    etcd = runner.run(config.api, config.etcd_check_command, check=False)
    if etcd.returncode == 0 and "etcd_quorum_status=passed members=3" in etcd.stdout:
        report.pass_check("etcd quorum has three healthy members")
    else:
        detail = (etcd.stderr or etcd.stdout or "check failed").strip().replace("\n", " ")
        report.fail(f"etcd quorum check failed: {detail}")
    return report


def _print_report(report: Report) -> None:
    for message in report.ok:
        print(f"[patroni-production][ok] {message}")
    for message in report.failures:
        print(f"[patroni-production][fail] {message}")
    status = "failed" if report.failures else "passed"
    print(
        f"[patroni-production][summary] status={status} "
        f"ok={len(report.ok)} failures={len(report.failures)}"
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resolve-primary",
        action="store_true",
        help="Print only api or reserve after validating the two Patroni roles.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        config = load_config()
        runner = SshRunner(config.ssh_options)
        if args.resolve_primary:
            primary, _ = select_primary(config.nodes, probe_nodes(config, runner))
            print(primary.label)
            return 0
        report = perform_checks(config, runner)
    except (RuntimeError, ValueError) as exc:
        if args.resolve_primary:
            print(f"could not resolve Patroni primary: {exc}", file=sys.stderr)
        else:
            print(f"[patroni-production][fail] {exc}")
            print("[patroni-production][summary] status=failed ok=0 failures=1")
        return 2

    _print_report(report)
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
