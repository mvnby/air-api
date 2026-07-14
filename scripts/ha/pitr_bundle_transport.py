"""Deterministic, pinned stdin transport for PITR host release assets."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
from pathlib import Path
from typing import Callable, Sequence

try:
    from scripts.ha.pitr_bundle_executor_source import REMOTE_RELEASE_BUNDLE_EXECUTOR
    from scripts.ha.pitr_pinned_ssh import (
        PatroniNode, PinnedSshContext, ssh_args, ssh_subprocess_environment,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_bundle_executor_source import REMOTE_RELEASE_BUNDLE_EXECUTOR  # type: ignore[no-redef]
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PatroniNode, PinnedSshContext, ssh_args, ssh_subprocess_environment,
    )
MAX_RELEASE_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_RELEASE_ASSET_BYTES = 1024 * 1024
LIBEXEC_DIR = "/usr/local/libexec/mvn-pitr"
BASE_REMOTE_ASSET_MODES = {
    "/usr/local/sbin/mvn-postgres-pitr-upload": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-immutable-upload": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-upload-wal": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-basebackup": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-configure-env": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-provision-host": 0o755,
    "/usr/local/sbin/mvn_postgres_pitr_config_transaction.py": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-restore": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-restore-drill": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-status": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-remote-status": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-bootstrap": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-runtime-check": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-scheduled-runner": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-manual-runner": 0o755,
    "/usr/local/sbin/mvn-restore-drill-latest-db": 0o755,
    "/usr/local/sbin/mvn-restore-drill-latest-db-cleanup": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-tool-runner": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-artifact-security": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-wal-lineage": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-recovery-config": 0o755,
    "/usr/local/sbin/mvn_postgres_pitr_operation_guard.py": 0o755,
    "/usr/local/sbin/mvn_postgres_pitr_operation_cleanup.py": 0o755,
    f"{LIBEXEC_DIR}/install_postgres_pitr_units.sh": 0o755,
    f"{LIBEXEC_DIR}/run_postgres_pitr_install_locked.py": 0o755,
    f"{LIBEXEC_DIR}/deploy_backend_blue_green.sh": 0o755,
    f"{LIBEXEC_DIR}/deploy_backend_blue_green_safety.sh": 0o755,
    f"{LIBEXEC_DIR}/safe_deploy_lock.py": 0o755,
    f"{LIBEXEC_DIR}/prepare_google_oauth_token_dir.sh": 0o755,
    "/etc/systemd/system/mvn-postgres-wal-upload.service": 0o644,
    "/etc/systemd/system/mvn-postgres-wal-upload.timer": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.service": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.timer": 0o644,
}
PROJECT_COMPOSE_PATHS = {
    "/opt/air-api": "/opt/air-api/docker-compose.patroni.yml",
    "/opt/mvn-reserve": "/opt/mvn-reserve/docker-compose.patroni.yml",
}
def expected_remote_asset_modes(node: PatroniNode) -> dict[str, int]:
    compose_path = PROJECT_COMPOSE_PATHS.get(node.project_dir)
    if compose_path != f"{node.project_dir}/{node.compose_file}":
        raise RuntimeError("unreviewed node compose destination")
    return {**BASE_REMOTE_ASSET_MODES, compose_path: 0o644}
def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
def _read_local_asset(path: Path) -> bytes:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o022
        or metadata.st_size > MAX_RELEASE_ASSET_BYTES
    ):
        raise RuntimeError(f"PITR release source metadata is unsafe: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if tuple(getattr(opened, name) for name in fields) != tuple(getattr(metadata, name) for name in fields):
            raise RuntimeError(f"PITR release source changed while opening: {path}")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, 131072)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_RELEASE_ASSET_BYTES:
                raise RuntimeError(f"PITR release source is too large: {path}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if tuple(getattr(after, name) for name in fields) != tuple(getattr(opened, name) for name in fields):
            raise RuntimeError(f"PITR release source changed while reading: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)
def build_release_bundle(node: PatroniNode, assets: Sequence[object]) -> str:
    """Build one canonical, complete node release bundle from reviewed assets."""
    expected = expected_remote_asset_modes(node)
    node_assets = [
        *assets,
        type("NodeComposeAsset", (), {
            "source": node.compose_source,
            "remote_path": f"{node.project_dir}/{node.compose_file}",
            "mode": 0o644,
        })(),
    ]
    by_path: dict[str, object] = {}
    for asset in node_assets:
        remote_path = getattr(asset, "remote_path", None)
        mode = getattr(asset, "mode", None)
        if remote_path not in expected or mode != expected.get(remote_path):
            raise RuntimeError(f"unreviewed PITR release asset: {remote_path}")
        if remote_path in by_path:
            raise RuntimeError(f"duplicate PITR release asset: {remote_path}")
        by_path[remote_path] = asset
    if set(by_path) != set(expected):
        raise RuntimeError("PITR release bundle has a missing or extra path")
    files = []
    for remote_path in sorted(by_path):
        content = _read_local_asset(Path(getattr(by_path[remote_path], "source")))
        files.append(
            {
                "content": base64.b64encode(content).decode("ascii"),
                "mode": expected[remote_path],
                "path": remote_path,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    body = {"files": files, "project_dir": node.project_dir, "version": 1}
    bundle = {**body, "release_sha256": hashlib.sha256(_canonical_json(body)).hexdigest()}
    rendered = _canonical_json(bundle)
    if not rendered or len(rendered) > MAX_RELEASE_BUNDLE_BYTES:
        raise RuntimeError("PITR release bundle exceeds the transport limit")
    return rendered.decode("ascii")
Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]
def _default_runner(args: Sequence[str], stdin: str | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env=ssh_subprocess_environment(),
    )
def run_remote_release_action(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    action: str,
    txid: str,
    assets: Sequence[object],
    runner: Runner | None = None,
) -> str:
    """Apply, roll back, or finalize one release over pinned SSH."""
    if action not in {"apply", "rollback", "finalize"}:
        raise RuntimeError("unsupported release transaction action")
    if not re.fullmatch(r"[0-9a-f]{32}", txid):
        raise RuntimeError("transaction id must be 32 lowercase hexadecimal characters")
    stdin = build_release_bundle(node, assets) if action == "apply" else None
    command = " ".join(
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            shlex.quote(REMOTE_RELEASE_BUNDLE_EXECUTOR),
            action,
            txid,
            shlex.quote(node.project_dir),
            shlex.quote(node.compose_file),
        ]
    )
    result = (runner or _default_runner)([*ssh_args(node, context), command], stdin)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "remote release action failed").strip()
        raise RuntimeError(detail)
    expected = {
        "apply": {"applied\n", "reopened\n"},
        "rollback": {"rolled-back\n", "already-rolled-back\n"},
        "finalize": {"finalized\n", "already-finalized\n"},
    }[action]
    if result.stdout not in expected or result.stderr:
        raise RuntimeError("remote release action returned unexpected output")
    return result.stdout[:-1]
