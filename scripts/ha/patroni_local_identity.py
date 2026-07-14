#!/usr/bin/env python3
"""Small fail-closed support contracts for the host Patroni role agent."""

from __future__ import annotations

import json
import math
import os
import re
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


PRIMARY_ROLES = {"leader", "master", "primary"}
REPLICA_ROLES = {"replica", "standby"}
EXPECTED_CLUSTER_NAMES = frozenset({"mvn-api", "zakup"})
MAINTENANCE_MARKER_PATH = Path("/run/mvn-postgres-pitr-maintenance")
MAINTENANCE_TRANSACTION_RE = re.compile(rb"[0-9a-f]{32}\n\Z")


def integer_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def render_role_env(role: str, *, bot_process: bool) -> str:
    primary = role == "primary"
    values = {
        "APP_ROLE": role,
        "API_READY_ENABLED": "false" if bot_process else str(primary).lower(),
        "BOT_ENABLED": str(primary and bot_process).lower(),
        "DB_BOOTSTRAP_ENABLED": "false",
        "SCHEDULER_ENABLED": str(primary and not bot_process).lower(),
    }
    if not primary:
        values.update(
            {
                "MAIL_IMAP_AUTO_IMPORT_ENABLED": "false",
                "MAIL_IMAP_LEAD_AUTO_IMPORT_ENABLED": "false",
                "CLOUDFLARE_PURGE_ENABLED": "false",
                "CLOUDFLARE_PURGE_DRY_RUN": "true",
            }
        )
    return "".join(f"{name}={value}\n" for name, value in values.items())


def atomic_write(path: Path, content: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def resolve_app_service(config: Any) -> str:
    if config.app_service:
        return config.app_service
    try:
        slot = config.active_slot_file.read_text(encoding="utf-8").strip().lower()
    except FileNotFoundError:
        slot = ""
    return f"app-{slot}" if slot in {"blue", "green"} else "app"


def wait_primary_ready(config: Any) -> None:
    for _ in range(config.ready_attempts):
        try:
            with urllib.request.urlopen(config.ready_url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if (
                response.status == 200
                and payload.get("api") == "ready"
                and payload.get("database_writable") is True
            ):
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise RuntimeError(f"primary API did not become ready: {config.ready_url}")


def systemd_units_match(config: Any, role: str) -> bool:
    """Require exact steady systemd state for the reviewed primary-only units."""

    expected_active = role == "primary"
    units = list(config.primary_systemd_units)
    if role == "standby":
        units.extend(
            unit.removesuffix(".timer") + ".service"
            for unit in config.primary_systemd_units
            if unit.endswith(".timer")
        )
    for unit in dict.fromkeys(units):
        try:
            result = subprocess.run(
                ["systemctl", "show", "--property=ActiveState", "--value", unit],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        expected_state = "active" if expected_active else "inactive"
        if result.returncode != 0 or result.stdout.strip() != expected_state:
            return False
        if unit.endswith(".timer"):
            try:
                enabled = subprocess.run(
                    ["systemctl", "is-enabled", unit],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (OSError, subprocess.SubprocessError):
                return False
            expected_enabled = "enabled" if expected_active else "disabled"
            expected_codes = {0} if expected_active else {0, 1}
            if (
                enabled.returncode not in expected_codes
                or enabled.stdout.strip() != expected_enabled
            ):
                return False
    return True


def reconcile_primary_systemd_units(
    config: Any,
    role: str,
    *,
    primary_guard: Callable[[str], None] | None = None,
    state_probe: Callable[[Any, str], bool] = systemd_units_match,
) -> None:
    """Converge timers and their services, escalating standby fencing if needed."""

    units = list(config.primary_systemd_units)
    if role == "standby":
        units.extend(
            unit.removesuffix(".timer") + ".service"
            for unit in config.primary_systemd_units
            if unit.endswith(".timer")
        )
    unique_units = tuple(dict.fromkeys(units))
    failures: list[str] = []
    for unit in unique_units:
        if role == "primary":
            if primary_guard is None:
                raise RuntimeError("primary systemd activation requires a Patroni guard")
            primary_guard(unit)
        if role == "primary" and unit.endswith(".timer"):
            command = ["systemctl", "enable", "--now", unit]
        elif role == "standby" and unit.endswith(".timer"):
            command = ["systemctl", "disable", "--now", "--no-block", unit]
        else:
            command = [
                "systemctl",
                "start" if role == "primary" else "stop",
                *(["--no-block"] if role == "standby" else []),
                unit,
            ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            failures.append(unit)
            continue
        if result.returncode != 0:
            failures.append(unit)
    if role == "standby":
        # ``systemctl stop`` deliberately does not clear a unit's failed latch.
        # A failed one-shot PITR service has no running owner, but the strict
        # steady-state probe still requires ``inactive``.  Clear only the
        # recorded failure after every stop attempt, then let the exact state
        # probe below prove that timers are disabled and every unit is inactive.
        for unit in unique_units:
            try:
                subprocess.run(
                    ["systemctl", "reset-failed", unit],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not state_probe(config, role):
            time.sleep(0.1)
        if not state_probe(config, role):
            for unit in unique_units:
                subprocess.run(
                    [
                        "systemctl",
                        "kill",
                        "--kill-whom=all",
                        "--signal=SIGKILL",
                        unit,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                subprocess.run(
                    ["systemctl", "stop", "--no-block", unit],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                subprocess.run(
                    ["systemctl", "reset-failed", unit],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not state_probe(config, role):
                time.sleep(0.1)
        if failures or not state_probe(config, role):
            raise RuntimeError(
                "could not fence primary-only systemd units: "
                + ",".join(failures or unique_units)
            )
    elif failures:
        raise RuntimeError(
            "could not start primary-only systemd units: " + ",".join(failures)
        )


def read_maintenance_transaction_id() -> str | None:
    """Securely read the exact root-owned PITR maintenance marker."""

    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(MAINTENANCE_MARKER_PATH, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError(f"unsafe PITR maintenance marker: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        metadata = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_gid,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_uid != 0
            or before.st_gid != 0
            or before.st_nlink != 1
            or before.st_size != 33
        ):
            raise RuntimeError("unsafe PITR maintenance marker metadata")
        content = os.read(descriptor, 34)
        after = os.fstat(descriptor)
        if metadata != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise RuntimeError("PITR maintenance marker changed while being read")
        if not MAINTENANCE_TRANSACTION_RE.fullmatch(content):
            raise RuntimeError("unsafe PITR maintenance marker content")
        return content[:-1].decode("ascii")
    finally:
        os.close(descriptor)


def _endpoint_url(patroni_url: str, endpoint: str) -> str:
    parsed = urllib.parse.urlsplit(patroni_url)
    if parsed.path.rstrip("/") != "/patroni" or parsed.query or parsed.fragment:
        raise ValueError("Patroni URL must end with /patroni and contain no query")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{endpoint.lstrip('/')}", "", "")
    )


def _fetch_json(url: str, *, timeout: float) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected Patroni response from {url}")
    return payload


def _validated_role(
    payload: dict[str, object],
    *,
    expected_name: str,
    expected_scope: str,
    max_dcs_age_seconds: int,
    now: float | None = None,
) -> str:
    state = str(payload.get("state") or "").strip().lower()
    if state != "running":
        raise ValueError(f"Patroni state is {state or '<empty>'}, expected running")
    metadata = payload.get("patroni")
    if not isinstance(metadata, dict):
        raise ValueError("Patroni identity metadata is missing")
    name = str(metadata.get("name") or "").strip()
    top_level_name = str(payload.get("name") or "").strip()
    scope = str(metadata.get("scope") or "").strip()
    if name != expected_name:
        raise ValueError(f"Patroni name is {name or '<empty>'}, expected {expected_name}")
    if top_level_name and top_level_name != expected_name:
        raise ValueError(
            f"Patroni top-level name is {top_level_name}, expected {expected_name}"
        )
    if scope != expected_scope:
        raise ValueError(
            f"Patroni scope is {scope or '<empty>'}, expected {expected_scope}"
        )
    unsafe_flags = {
        "pending_restart": "pending restart",
        "pause": "cluster pause",
        "cluster_unlocked": "missing DCS leader lock",
        "failsafe_mode_is_active": "DCS failsafe mode",
    }
    for field, description in unsafe_flags.items():
        if field in payload and payload[field] is not False:
            raise ValueError(f"Patroni reports {description}")
    observed_at = payload.get("dcs_last_seen")
    if (
        isinstance(observed_at, bool)
        or not isinstance(observed_at, (int, float))
        or not math.isfinite(float(observed_at))
    ):
        raise ValueError("Patroni DCS observation timestamp is missing")
    age = (time.time() if now is None else now) - float(observed_at)
    if age < 0 or age > max_dcs_age_seconds:
        raise ValueError(f"Patroni DCS observation is stale (age={age:.3f}s)")
    role = str(payload.get("role") or "").strip().lower()
    if role in PRIMARY_ROLES:
        return "primary"
    if role in REPLICA_ROLES:
        return "standby"
    raise ValueError(f"unsupported Patroni role: {role or '<empty>'}")


def _validate_leader_lock(
    status: dict[str, object],
    leader: dict[str, object],
    cluster: dict[str, object],
    *,
    expected_name: str,
    expected_scope: str,
    max_dcs_age_seconds: int,
) -> None:
    if _validated_role(
        leader,
        expected_name=expected_name,
        expected_scope=expected_scope,
        max_dcs_age_seconds=max_dcs_age_seconds,
    ) != "primary":
        raise ValueError("Patroni /leader endpoint did not return the local primary")
    for field in ("timeline", "database_system_identifier"):
        value = status.get(field)
        if value in (None, "") or leader.get(field) != value:
            raise ValueError(f"Patroni /leader disagrees with /patroni on {field}")
    timeline = status.get("timeline")
    if isinstance(timeline, bool) or not isinstance(timeline, int) or timeline <= 0:
        raise ValueError("Patroni primary timeline is missing or invalid")
    raw_members = cluster.get("members")
    if not isinstance(raw_members, list) or not all(
        isinstance(member, dict) for member in raw_members
    ):
        raise ValueError("Patroni /cluster member list is missing or invalid")
    names = [str(member.get("name") or "").strip() for member in raw_members]
    if set(names) != EXPECTED_CLUSTER_NAMES or len(names) != len(EXPECTED_CLUSTER_NAMES):
        raise ValueError(f"Patroni /cluster identities are unsafe: {sorted(names)}")
    leaders = [
        member
        for member in raw_members
        if str(member.get("role") or "").strip().lower() in PRIMARY_ROLES
    ]
    if len(leaders) != 1:
        raise ValueError(f"Patroni /cluster reports {len(leaders)} DCS leaders")
    local_leader = leaders[0]
    if str(local_leader.get("name") or "").strip() != expected_name:
        raise ValueError("Patroni DCS leader identity is not the local node")
    if str(local_leader.get("state") or "").strip().lower() != "running":
        raise ValueError("Patroni DCS leader is not running")
    if (
        "pending_restart" in local_leader
        and local_leader["pending_restart"] is not False
    ):
        raise ValueError("Patroni DCS leader has a pending restart")
    if local_leader.get("timeline") != timeline:
        raise ValueError("Patroni DCS leader timeline disagrees with local Patroni")


def fetch_patroni_role(
    url: str,
    *,
    expected_name: str,
    expected_scope: str,
    max_dcs_age_seconds: int,
    timeout: float = 3.0,
) -> str:
    """Return the safe role; primary requires fresh local and DCS lock proof."""

    status = _fetch_json(url, timeout=timeout)
    role = _validated_role(
        status,
        expected_name=expected_name,
        expected_scope=expected_scope,
        max_dcs_age_seconds=max_dcs_age_seconds,
    )
    if role == "primary":
        leader = _fetch_json(_endpoint_url(url, "leader"), timeout=timeout)
        cluster = _fetch_json(_endpoint_url(url, "cluster"), timeout=timeout)
        _validate_leader_lock(
            status,
            leader,
            cluster,
            expected_name=expected_name,
            expected_scope=expected_scope,
            max_dcs_age_seconds=max_dcs_age_seconds,
        )
    return role
