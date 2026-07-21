#!/usr/bin/env python3
"""Fail-closed detection of the official two-node Patroni maintenance window."""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence


MAINTENANCE_TRANSACTION_RE = re.compile(r"[0-9a-f]{32}")
DEFAULT_MAX_AGE_SECONDS = 2 * 60 * 60
MAX_FUTURE_SKEW_SECONDS = 60
PITR_TIMERS = (
    "mvn-postgres-wal-upload.timer",
    "mvn-postgres-basebackup.timer",
)


REMOTE_PROBE = r'''import json
import os
import re
import stat
import subprocess

MARKER = "/run/mvn-postgres-pitr-maintenance"
TRANSACTION_RE = re.compile(rb"[0-9a-f]{32}\n")
ROLE_AGENT = "mvn-patroni-role-agent.service"
PITR_TIMERS = (
    "mvn-postgres-wal-upload.timer",
    "mvn-postgres-basebackup.timer",
)


def generation(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def emit(payload):
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def invalid(message):
    emit({"status": "invalid", "error": message})
    raise SystemExit(0)


try:
    before = os.lstat(MARKER)
except FileNotFoundError:
    emit({"status": "absent"})
    raise SystemExit(0)
except OSError:
    invalid("maintenance marker metadata cannot be read")

if (
    not stat.S_ISREG(before.st_mode)
    or stat.S_ISLNK(before.st_mode)
    or stat.S_IMODE(before.st_mode) != 0o600
    or before.st_uid != 0
    or before.st_gid != 0
    or before.st_nlink != 1
    or before.st_size != 33
):
    invalid("maintenance marker metadata is unsafe")

flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
try:
    descriptor = os.open(MARKER, flags)
except OSError:
    invalid("maintenance marker cannot be opened safely")
try:
    opened = os.fstat(descriptor)
    if generation(opened) != generation(before):
        invalid("maintenance marker changed before open")
    content = os.read(descriptor, 34)
    after = os.fstat(descriptor)
    if generation(after) != generation(opened):
        invalid("maintenance marker changed while being read")
finally:
    os.close(descriptor)

try:
    final = os.lstat(MARKER)
except OSError:
    invalid("maintenance marker path changed while being read")
if generation(final) != generation(after):
    invalid("maintenance marker path changed while being read")
if TRANSACTION_RE.fullmatch(content) is None:
    invalid("maintenance marker content is invalid")


def active_state(unit):
    result = subprocess.run(
        ["/usr/bin/systemctl", "is-active", unit],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip() or "unknown"


role_agent_state = active_state(ROLE_AGENT)
timer_states = {timer: active_state(timer) for timer in PITR_TIMERS}
if role_agent_state != "active":
    invalid("Patroni role agent is not active during maintenance")
if any(state != "inactive" for state in timer_states.values()):
    invalid("PITR timers are not fenced during maintenance")

emit(
    {
        "status": "active",
        "transaction_id": content[:-1].decode("ascii"),
        "mtime_ns": final.st_mtime_ns,
        "role_agent_state": role_agent_state,
        "timer_states": timer_states,
    }
)
'''


@dataclass(frozen=True)
class NodeObservation:
    label: str
    status: str
    transaction_id: str = ""
    mtime_ns: int = 0


@dataclass(frozen=True)
class MaintenanceWindow:
    active: bool
    transaction_id: str = ""
    age_seconds: int = 0


RemoteRunner = Callable[[str, str], subprocess.CompletedProcess[str]]


def parse_observation(label: str, result: subprocess.CompletedProcess[str]) -> NodeObservation:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "remote marker probe failed").strip()
        raise RuntimeError(f"{label}: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label}: invalid maintenance probe response") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"{label}: invalid maintenance probe response")
    status = payload.get("status")
    if status == "absent":
        if set(payload) != {"status"}:
            raise RuntimeError(f"{label}: unexpected absent marker response")
        return NodeObservation(label=label, status="absent")
    if status == "invalid":
        error = payload.get("error")
        if not isinstance(error, str) or not error:
            error = "official maintenance marker is invalid"
        raise RuntimeError(f"{label}: {error}")
    if status != "active":
        raise RuntimeError(f"{label}: unsupported maintenance marker status")

    expected_keys = {
        "status",
        "transaction_id",
        "mtime_ns",
        "role_agent_state",
        "timer_states",
    }
    if set(payload) != expected_keys:
        raise RuntimeError(f"{label}: unexpected active maintenance probe response")

    transaction_id = payload.get("transaction_id")
    mtime_ns = payload.get("mtime_ns")
    role_agent_state = payload.get("role_agent_state")
    timer_states = payload.get("timer_states")
    if (
        not isinstance(transaction_id, str)
        or MAINTENANCE_TRANSACTION_RE.fullmatch(transaction_id) is None
        or not isinstance(mtime_ns, int)
        or isinstance(mtime_ns, bool)
        or mtime_ns <= 0
        or role_agent_state != "active"
        or not isinstance(timer_states, Mapping)
        or set(timer_states) != set(PITR_TIMERS)
        or any(timer_states[timer] != "inactive" for timer in PITR_TIMERS)
    ):
        raise RuntimeError(f"{label}: invalid active maintenance probe response")
    return NodeObservation(
        label=label,
        status="active",
        transaction_id=transaction_id,
        mtime_ns=mtime_ns,
    )


def evaluate_window(
    observations: Sequence[NodeObservation],
    *,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    now_ns: int | None = None,
) -> MaintenanceWindow:
    if len(observations) != 2 or len({item.label for item in observations}) != 2:
        raise RuntimeError("maintenance proof requires exactly two distinct nodes")
    if max_age_seconds < 60:
        raise RuntimeError("maintenance maximum age must be at least 60 seconds")
    statuses = {item.status for item in observations}
    if statuses == {"absent"}:
        return MaintenanceWindow(active=False)
    if statuses != {"active"}:
        rendered = ", ".join(f"{item.label}={item.status}" for item in observations)
        raise RuntimeError(f"partial Patroni maintenance window: {rendered}")

    transaction_ids = {item.transaction_id for item in observations}
    if len(transaction_ids) != 1:
        raise RuntimeError("Patroni nodes have different maintenance transactions")
    current_ns = time.time_ns() if now_ns is None else now_ns
    ages = [(current_ns - item.mtime_ns) / 1_000_000_000 for item in observations]
    if any(age < -MAX_FUTURE_SKEW_SECONDS for age in ages):
        raise RuntimeError("Patroni maintenance marker timestamp is in the future")
    oldest_age = max(0, int(max(ages)))
    if oldest_age > max_age_seconds:
        raise RuntimeError(
            f"Patroni maintenance window is stale: age={oldest_age}s "
            f"limit={max_age_seconds}s"
        )
    return MaintenanceWindow(
        active=True,
        transaction_id=next(iter(transaction_ids)),
        age_seconds=oldest_age,
    )


def detect_window(
    nodes: Sequence[tuple[str, str]],
    *,
    runner: RemoteRunner,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    now_ns: int | None = None,
) -> MaintenanceWindow:
    observations = []
    for label, target in nodes:
        result = runner(target, REMOTE_PROBE)
        observations.append(parse_observation(label, result))
    return evaluate_window(
        observations,
        max_age_seconds=max_age_seconds,
        now_ns=now_ns,
    )
