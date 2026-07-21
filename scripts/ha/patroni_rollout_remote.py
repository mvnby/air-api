"""Pinned transport for the root-only Patroni rollout executor."""

from __future__ import annotations

import hashlib
import base64
import json
import os
import shlex
import stat
import subprocess
from pathlib import Path
from typing import Callable, Mapping, Sequence

try:
    from scripts.ha.patroni_rollout_remote_executor import REMOTE_EXECUTOR
    from scripts.ha.patroni_rollout_schema import (
        LEGACY_ARCHIVE_COMMAND_SHA256,
        RolloutInputs,
        canonical_json,
    )
    from scripts.ha.pitr_pinned_ssh import PatroniNode, PinnedSshContext, ssh_args
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from patroni_rollout_remote_executor import REMOTE_EXECUTOR  # type: ignore[no-redef]
    from patroni_rollout_schema import (  # type: ignore[no-redef]
        LEGACY_ARCHIVE_COMMAND_SHA256,
        RolloutInputs,
        canonical_json,
    )
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PatroniNode,
        PinnedSshContext,
        ssh_args,
    )


Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]
REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_SOURCE = REPO_ROOT / "deploy/ha/patroni/archive_wal.py"
CONTRACT_SOURCE = REPO_ROOT / "scripts/ha/patroni_compose_db_contract.py"
ETCD_CHECK_SOURCE = REPO_ROOT / "scripts/ha/check_etcd_quorum.sh"
ROLE_AGENT_SOURCE = REPO_ROOT / "scripts/ha/patroni_role_agent.py"
ROLE_IDENTITY_SOURCE = REPO_ROOT / "scripts/ha/patroni_local_identity.py"
ROLE_UNIT_SOURCE = REPO_ROOT / "deploy/ha/patroni/mvn-patroni-role-agent.service"
ACTIONS = {
    "abort",
    "apply-archive-command",
    "attest-target-runtime",
    "attest-archive-runtime",
    "attest-current-runtime",
    "attest-runtime-ownership",
    "check-baseline-dcs",
    "check-legacy-dcs",
    "check-target-dcs",
    "finalize",
    "journal-status",
    "prepare",
    "preflight",
    "prove-etcd",
    "prove-archive",
    "record",
    "revert-archive-command",
    "rollback-node",
    "stage",
    "status",
    "switchover",
    "update-node",
}
ACTION_EXTRAS = {
    "prepare": {"baseline_primary", "baseline_system_identifier", "baseline_timeline"},
    "record": {"record"},
    "stage": {"ghcr_token", "ghcr_username"},
    "switchover": {"candidate", "expected_primary"},
    "update-node": {"expected_primary", "expected_role", "update_phase"},
    "rollback-node": {"expected_primary", "expected_role", "update_phase"},
    "attest-runtime-ownership": {"expected_role"},
}


def _default_runner(
    args: Sequence[str], stdin: str | None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=900,
    )


def _read_local_asset(path: Path) -> bytes:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise RuntimeError("local Patroni WAL helper source is unsafe")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if tuple(getattr(opened, field) for field in fields) != tuple(getattr(metadata, field) for field in fields):
            raise RuntimeError("local rollout asset changed while opening")
        chunks = []
        while True:
            chunk = os.read(descriptor, 131072)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if tuple(getattr(after, field) for field in fields) != tuple(getattr(opened, field) for field in fields):
            raise RuntimeError("local rollout asset changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def helper_source_sha256(path: Path = HELPER_SOURCE) -> str:
    return hashlib.sha256(_read_local_asset(path)).hexdigest()


def build_payload(
    *,
    inputs: RolloutInputs,
    action: str,
    compose_contract_sha256: str,
    helper_sha256: str,
    extra: Mapping[str, str] | None = None,
) -> str:
    contract_source = _read_local_asset(CONTRACT_SOURCE)
    etcd_source = _read_local_asset(ETCD_CHECK_SOURCE)
    role_agent_source = _read_local_asset(ROLE_AGENT_SOURCE)
    role_identity_source = _read_local_asset(ROLE_IDENTITY_SOURCE)
    role_unit_source = _read_local_asset(ROLE_UNIT_SOURCE)
    payload: dict[str, object] = {
        "compose_contract_sha256": compose_contract_sha256,
        "contract_helper_b64": base64.b64encode(contract_source).decode("ascii"),
        "contract_helper_sha256": hashlib.sha256(contract_source).hexdigest(),
        "controller_sha256": hashlib.sha256(REMOTE_EXECUTOR.encode()).hexdigest(),
        "current_image": inputs.current_image,
        "deploy_sha": inputs.deploy_sha,
        "publish_run_attempt": inputs.publish_run_attempt,
        "publish_run_id": inputs.publish_run_id,
        "etcd_check_b64": base64.b64encode(etcd_source).decode("ascii"),
        "etcd_check_sha256": hashlib.sha256(etcd_source).hexdigest(),
        "helper_sha256": helper_sha256,
        "legacy_command_sha256": LEGACY_ARCHIVE_COMMAND_SHA256,
        "maintenance_transaction_id": inputs.maintenance_transaction_id,
        "resume": inputs.resume,
        "role_agent_sha256": hashlib.sha256(role_agent_source).hexdigest(),
        "role_identity_sha256": hashlib.sha256(role_identity_source).hexdigest(),
        "role_unit_sha256": hashlib.sha256(role_unit_source).hexdigest(),
        "target_image": inputs.target_image,
    }
    if extra:
        allowed = ACTION_EXTRAS.get(action, set())
        if set(extra) - allowed or set(extra) & set(payload):
            raise RuntimeError(f"unreviewed payload fields for {action}")
        payload.update(extra)
    return canonical_json(payload)


def run_remote_action(
    *,
    action: str,
    node: PatroniNode,
    context: PinnedSshContext,
    inputs: RolloutInputs,
    compose_contract_sha256: str,
    helper_sha256: str,
    extra: Mapping[str, str] | None = None,
    runner: Runner | None = None,
) -> str:
    if action not in ACTIONS:
        raise RuntimeError(f"unsupported Patroni rollout action: {action}")
    command = " ".join(
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            shlex.quote(REMOTE_EXECUTOR),
            action,
            node.alias,
            inputs.transaction_id,
        ]
    )
    payload = build_payload(
        inputs=inputs,
        action=action,
        compose_contract_sha256=compose_contract_sha256,
        helper_sha256=helper_sha256,
        extra=extra,
    )
    result = (runner or _default_runner)([*ssh_args(node, context), command], payload)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "remote rollout failed").strip()
        raise RuntimeError(f"{node.alias} {action}: {detail}")
    return result.stdout.strip()


def read_status(**kwargs: object) -> dict[str, object]:
    raw = run_remote_action(action="journal-status", **kwargs)  # type: ignore[arg-type]
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("remote rollout status is invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("remote rollout status is not an object")
    return value
