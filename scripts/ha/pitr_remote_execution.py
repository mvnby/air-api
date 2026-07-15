"""Locked remote execution for pinned PostgreSQL PITR operations."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

try:
    from scripts.ha.pitr_bundle_transport import (
        REMOTE_RELEASE_BUNDLE_EXECUTOR,
        build_release_bundle as _build_release_bundle,
        prepare_release_bundles as _prepare_release_bundles,
        _read_local_asset as _read_release_asset,
        run_remote_release_action as _run_remote_release_action,
    )
    from scripts.ha.pitr_pinned_ssh import PatroniNode, PinnedSshContext, ssh_args
    from scripts.ha.pitr_remote_executors import (
        LOCKED_MAINTENANCE_WRAPPER,
        REMOTE_ASSET_ATTESTATION,
        REMOTE_MAINTENANCE_EXECUTOR,
        REMOTE_ROLE_AGENT_EXECUTOR,
        REMOTE_SECRET_EXECUTOR,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_bundle_transport import (  # type: ignore[no-redef]
        REMOTE_RELEASE_BUNDLE_EXECUTOR,
        build_release_bundle as _build_release_bundle,
        prepare_release_bundles as _prepare_release_bundles,
        _read_local_asset as _read_release_asset,
        run_remote_release_action as _run_remote_release_action,
    )
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PatroniNode,
        PinnedSshContext,
        ssh_args,
    )
    from pitr_remote_executors import (  # type: ignore[no-redef]
        LOCKED_MAINTENANCE_WRAPPER,
        REMOTE_ASSET_ATTESTATION,
        REMOTE_MAINTENANCE_EXECUTOR,
        REMOTE_ROLE_AGENT_EXECUTOR,
        REMOTE_SECRET_EXECUTOR,
    )


Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]
REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSACTION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ROLE_AGENT_PHASES = {
    "quiesce-fenced",
    "quiesce-standby",
    "resume-primary",
    "resume-standby",
}


@dataclass(frozen=True)
class PitrHostAsset:
    source: Path
    remote_path: str
    mode: int


PITR_HOST_ASSETS = (
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/upload_postgres_pitr_to_s3.py",
        "/usr/local/sbin/mvn-postgres-pitr-upload",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/postgres_pitr_immutable_upload.py",
        "/usr/local/sbin/mvn-postgres-pitr-immutable-upload",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/upload_postgres_pitr_wal.sh",
        "/usr/local/sbin/mvn-postgres-pitr-upload-wal",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/create_postgres_pitr_basebackup.sh",
        "/usr/local/sbin/mvn-postgres-pitr-basebackup",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/configure_postgres_pitr_env.py",
        "/usr/local/sbin/mvn-postgres-pitr-configure-env",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/provision_postgres_pitr_host.py",
        "/usr/local/sbin/mvn-postgres-pitr-provision-host",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/pitr_config_transaction.py",
        "/usr/local/sbin/mvn_postgres_pitr_config_transaction.py",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/restore_postgres_pitr_from_s3.py",
        "/usr/local/sbin/mvn-postgres-pitr-restore",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/restore_postgres_pitr_drill.sh",
        "/usr/local/sbin/mvn-postgres-pitr-restore-drill",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/check_postgres_pitr_status.sh",
        "/usr/local/sbin/mvn-postgres-pitr-status",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/check_postgres_pitr_remote.py",
        "/usr/local/sbin/mvn-postgres-pitr-remote-status",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/bootstrap_postgres_pitr.sh",
        "/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/verify_postgres_pitr_runtime.py",
        "/usr/local/sbin/mvn-postgres-pitr-runtime-check",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/run_postgres_pitr_scheduled.py",
        "/usr/local/sbin/mvn-postgres-pitr-scheduled-runner",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/run_postgres_pitr_manual.py",
        "/usr/local/sbin/mvn-postgres-pitr-manual-runner",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/calculate_logical_restore_resources.py",
        "/usr/local/sbin/mvn-logical-restore-resource-sizer",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/restore_drill_latest_db.sh",
        "/usr/local/sbin/mvn-restore-drill-latest-db",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/cleanup_restore_drill_runtime.sh",
        "/usr/local/sbin/mvn-restore-drill-latest-db-cleanup",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/run_postgres_pitr_tool.py",
        "/usr/local/sbin/mvn-postgres-pitr-tool-runner",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/postgres_pitr_artifact_security.py",
        "/usr/local/sbin/mvn-postgres-pitr-artifact-security",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/postgres_pitr_wal_lineage.py",
        "/usr/local/sbin/mvn-postgres-pitr-wal-lineage",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/postgres_pitr_recovery_config.py",
        "/usr/local/sbin/mvn-postgres-pitr-recovery-config",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/pitr_operation_guard.py",
        "/usr/local/sbin/mvn_postgres_pitr_operation_guard.py",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/pitr_operation_cleanup.py",
        "/usr/local/sbin/mvn_postgres_pitr_operation_cleanup.py",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/install_postgres_pitr_units.sh",
        "/usr/local/libexec/mvn-pitr/install_postgres_pitr_units.sh",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/run_postgres_pitr_install_locked.py",
        "/usr/local/libexec/mvn-pitr/run_postgres_pitr_install_locked.py",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/deploy_backend_blue_green.sh",
        "/usr/local/libexec/mvn-pitr/deploy_backend_blue_green.sh",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/deploy_backend_blue_green_safety.sh",
        "/usr/local/libexec/mvn-pitr/deploy_backend_blue_green_safety.sh",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/require_deploy_capacity.sh",
        "/usr/local/libexec/mvn-pitr/require_deploy_capacity.sh",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/verify_pitr_maintenance_marker.py",
        "/usr/local/libexec/mvn-pitr/verify_pitr_maintenance_marker.py",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/safe_deploy_lock.py",
        "/usr/local/libexec/mvn-pitr/safe_deploy_lock.py",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/prepare_google_oauth_token_dir.sh",
        "/usr/local/libexec/mvn-pitr/prepare_google_oauth_token_dir.sh",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "deploy/ha/systemd/mvn-postgres-wal-upload.service",
        "/etc/systemd/system/mvn-postgres-wal-upload.service",
        0o644,
    ),
    PitrHostAsset(
        REPO_ROOT / "deploy/ha/systemd/mvn-postgres-wal-upload.timer",
        "/etc/systemd/system/mvn-postgres-wal-upload.timer",
        0o644,
    ),
    PitrHostAsset(
        REPO_ROOT / "deploy/ha/systemd/mvn-postgres-basebackup.service",
        "/etc/systemd/system/mvn-postgres-basebackup.service",
        0o644,
    ),
    PitrHostAsset(
        REPO_ROOT / "deploy/ha/systemd/mvn-postgres-basebackup.timer",
        "/etc/systemd/system/mvn-postgres-basebackup.timer",
        0o644,
    ),
)

ROLE_AGENT_ASSETS = (
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/patroni_role_agent.py",
        "/usr/local/sbin/mvn-patroni-role-agent",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/patroni_local_identity.py",
        "/usr/local/sbin/patroni_local_identity.py",
        0o644,
    ),
    PitrHostAsset(
        REPO_ROOT / "deploy/ha/patroni/mvn-patroni-role-agent.service",
        "/etc/systemd/system/mvn-patroni-role-agent.service",
        0o644,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/pitr_operation_guard.py",
        "/usr/local/sbin/mvn_postgres_pitr_operation_guard.py",
        0o755,
    ),
    PitrHostAsset(
        REPO_ROOT / "scripts/ha/pitr_operation_cleanup.py",
        "/usr/local/sbin/mvn_postgres_pitr_operation_cleanup.py",
        0o755,
    ),
)


def render_host_asset_manifest(
    node: PatroniNode,
    assets: Sequence[PitrHostAsset] = PITR_HOST_ASSETS,
) -> str:
    node_assets = (
        *assets,
        PitrHostAsset(
            node.compose_source,
            f"{node.project_dir}/{node.compose_file}",
            0o644,
        ),
    )
    manifest: dict[str, str] = {}
    for asset in node_assets:
        metadata = asset.source.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"PITR host asset must be a regular non-symlink: {asset.source}")
        if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
            raise RuntimeError(f"PITR host asset has unsafe ownership or mode: {asset.source}")
        if asset.remote_path in manifest:
            raise RuntimeError(f"duplicate PITR host asset path: {asset.remote_path}")
        manifest[asset.remote_path] = hashlib.sha256(
            _read_release_asset(asset.source)
        ).hexdigest()
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"))


def render_role_agent_asset_manifest(
    assets: Sequence[PitrHostAsset] = ROLE_AGENT_ASSETS,
) -> str:
    manifest: dict[str, str] = {}
    for asset in assets:
        metadata = asset.source.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(
                f"role-agent asset must be a regular non-symlink: {asset.source}"
            )
        if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
            raise RuntimeError(f"role-agent asset has unsafe ownership or mode: {asset.source}")
        if asset.remote_path in manifest:
            raise RuntimeError(f"duplicate role-agent asset path: {asset.remote_path}")
        manifest[asset.remote_path] = hashlib.sha256(
            _read_release_asset(asset.source)
        ).hexdigest()
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"))


def build_host_release_bundle(
    node: PatroniNode,
    assets: Sequence[PitrHostAsset] = PITR_HOST_ASSETS,
) -> str:
    return _build_release_bundle(node, assets)


def prepare_host_release_bundles(
    nodes: Sequence[PatroniNode],
    assets: Sequence[PitrHostAsset] = PITR_HOST_ASSETS,
) -> dict[str, str]:
    return _prepare_release_bundles(nodes, assets)


def run_remote_release_action(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    action: str,
    txid: str,
    assets: Sequence[PitrHostAsset] = PITR_HOST_ASSETS,
    release_bundle: str | None = None,
    runner: Runner | None = None,
) -> str:
    return _run_remote_release_action(
        node=node,
        context=context,
        action=action,
        txid=txid,
        assets=assets,
        release_bundle=release_bundle,
        runner=runner,
    )


def _run_subprocess(
    args: Sequence[str], stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_checked(
    args: Sequence[str],
    *,
    stdin: str | None = None,
    runner: Runner | None = None,
) -> None:
    result = (runner or _run_subprocess)(args, stdin)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(output or f"command failed: {' '.join(args)}")
    output = result.stdout.strip()
    if output:
        print(output)


def run_remote_secret_phase(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    env_text: str,
    bootstrap_helper: str,
    phase: str,
    transaction_id: str,
    runner: Runner | None = None,
) -> None:
    if bootstrap_helper != "/usr/local/sbin/mvn-postgres-pitr-bootstrap":
        raise RuntimeError("unexpected bootstrap helper path")
    if phase not in {"preflight", "configure-node"}:
        raise RuntimeError(f"unsupported secret phase: {phase}")
    if not TRANSACTION_ID_RE.fullmatch(transaction_id):
        raise RuntimeError("PITR transaction ID must be 32 lowercase hexadecimal characters")
    asset_manifest = render_host_asset_manifest(node)
    locked_wrapper_digest = hashlib.sha256(
        LOCKED_MAINTENANCE_WRAPPER.encode()
    ).hexdigest()
    command = " ".join(
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            shlex.quote(REMOTE_SECRET_EXECUTOR),
            shlex.quote(bootstrap_helper),
            shlex.quote(phase),
            shlex.quote(node.project_dir),
            shlex.quote(node.compose_file),
            transaction_id,
            shlex.quote(asset_manifest),
            shlex.quote(LOCKED_MAINTENANCE_WRAPPER),
            locked_wrapper_digest,
        ]
    )
    _run_checked(
        [*ssh_args(node, context), command],
        stdin=env_text,
        runner=runner,
    )


def _run_remote_maintenance_phase(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    bootstrap_helper: str,
    phase: str,
    transaction_id: str,
    confirmation: str,
    runner: Runner | None = None,
) -> None:
    if bootstrap_helper != "/usr/local/sbin/mvn-postgres-pitr-bootstrap":
        raise RuntimeError("unexpected bootstrap helper path")
    if phase not in {
        "provision-node",
        "scrub-node",
        "basebackup",
        "enable-archive-env",
        "enable-timers",
        "restore-drill",
        "verify",
    }:
        raise RuntimeError(f"unsupported maintenance phase: {phase}")
    if not TRANSACTION_ID_RE.fullmatch(transaction_id):
        raise RuntimeError("PITR transaction ID must be 32 lowercase hexadecimal characters")
    if confirmation not in {"false", "fenced"}:
        raise RuntimeError("unsupported PITR maintenance confirmation")
    if confirmation == "fenced" and phase != "provision-node":
        raise RuntimeError("fenced maintenance is limited to provision-node")
    asset_manifest = render_host_asset_manifest(node)
    locked_wrapper_digest = hashlib.sha256(
        LOCKED_MAINTENANCE_WRAPPER.encode()
    ).hexdigest()
    command = " ".join(
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            shlex.quote(REMOTE_MAINTENANCE_EXECUTOR),
            shlex.quote(bootstrap_helper),
            shlex.quote(phase),
            shlex.quote(node.project_dir),
            shlex.quote(node.compose_file),
            confirmation,
            transaction_id,
            shlex.quote(asset_manifest),
            shlex.quote(LOCKED_MAINTENANCE_WRAPPER),
            locked_wrapper_digest,
        ]
    )
    _run_checked([*ssh_args(node, context), command], runner=runner)


def run_remote_maintenance_phase(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    bootstrap_helper: str,
    phase: str,
    transaction_id: str,
    runner: Runner | None = None,
) -> None:
    _run_remote_maintenance_phase(
        node=node,
        context=context,
        bootstrap_helper=bootstrap_helper,
        phase=phase,
        transaction_id=transaction_id,
        confirmation="false",
        runner=runner,
    )


def run_remote_fenced_provision_phase(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    bootstrap_helper: str,
    transaction_id: str,
    runner: Runner | None = None,
) -> None:
    _run_remote_maintenance_phase(
        node=node,
        context=context,
        bootstrap_helper=bootstrap_helper,
        phase="provision-node",
        transaction_id=transaction_id,
        confirmation="fenced",
        runner=runner,
    )


def run_remote_role_agent_phase(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    phase: str,
    transaction_id: str,
    runner: Runner | None = None,
) -> None:
    """Quiesce or safely reconcile the pinned Patroni role agent."""

    if phase not in ROLE_AGENT_PHASES:
        raise RuntimeError(f"unsupported role-agent phase: {phase}")
    if not TRANSACTION_ID_RE.fullmatch(transaction_id):
        raise RuntimeError("PITR transaction ID must be 32 lowercase hexadecimal characters")
    command = " ".join(
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            shlex.quote(REMOTE_ROLE_AGENT_EXECUTOR),
            shlex.quote(phase),
            shlex.quote(node.project_dir),
            transaction_id,
            shlex.quote(render_role_agent_asset_manifest()),
        ]
    )
    _run_checked([*ssh_args(node, context), command], runner=runner)
