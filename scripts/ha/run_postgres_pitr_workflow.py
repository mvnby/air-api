#!/usr/bin/env python3
"""Run a reviewed PITR workflow through pinned SSH and strict topology proof."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
_repo_import_index = next(
    (index for index, value in enumerate(sys.path) if "site-packages" in value),
    len(sys.path),
)
sys.path.insert(_repo_import_index, str(REPO_ROOT))

try:
    from scripts.ha.pitr_cluster_topology import (
        ClusterTopology,
        discover_cluster_topology,
    )
    from scripts.ha.pitr_pinned_ssh import (
        PATRONI_NODES,
        PatroniNode,
        PinnedSshContext,
        create_context,
        ssh_args,
        ssh_subprocess_environment,
        validate_effective_config,
    )
    from scripts.ha.pitr_remote_execution import build_host_release_bundle
    from scripts.ha.patroni_maintenance_window import REMOTE_PROBE, detect_window
    from scripts.ha.calculate_logical_restore_resources import (
        ResourceSizingError,
        calculate_resources,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_cluster_topology import (  # type: ignore[no-redef]
        ClusterTopology,
        discover_cluster_topology,
    )
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PATRONI_NODES,
        PatroniNode,
        PinnedSshContext,
        create_context,
        ssh_args,
        ssh_subprocess_environment,
        validate_effective_config,
    )
    from pitr_remote_execution import build_host_release_bundle  # type: ignore[no-redef]
    from patroni_maintenance_window import (  # type: ignore[no-redef]
        REMOTE_PROBE,
        detect_window,
    )
    from calculate_logical_restore_resources import (  # type: ignore[no-redef]
        ResourceSizingError,
        calculate_resources,
    )


Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]
MANUAL_RUNNER = "/usr/local/sbin/mvn-postgres-pitr-manual-runner"
MAX_IDENTITY_BYTES = 65536
BACKUP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TARGET_TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
LOGICAL_RESTORE_PREFERRED_ALIAS = "mvn-api"


class WorkflowError(RuntimeError):
    """A fail-closed workflow contract violation."""


class WorkflowArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(64, f"{self.prog}: error: {message}\n")


def _run_subprocess(
    args: Sequence[str], stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(args),
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
            env=ssh_subprocess_environment(),
        )
    except OSError as exc:
        return subprocess.CompletedProcess(list(args), 127, "", str(exc))


def _read_identity(stream: BinaryIO) -> bytes:
    payload = stream.read(MAX_IDENTITY_BYTES + 1)
    if not payload or len(payload) > MAX_IDENTITY_BYTES:
        raise WorkflowError("SSH identity payload size is invalid")
    if b"\0" in payload:
        raise WorkflowError("SSH identity payload is invalid")
    normalized = payload.rstrip(b"\r\n") + b"\n"
    lines = normalized.splitlines()
    if (
        len(lines) < 3
        or lines[0] != b"-----BEGIN OPENSSH PRIVATE KEY-----"
        or lines[-1] != b"-----END OPENSSH PRIVATE KEY-----"
        or any(not line for line in lines[1:-1])
    ):
        raise WorkflowError("SSH identity must be one OpenSSH private key")
    return normalized


def _write_identity(directory: Path, payload: bytes) -> Path:
    identity = directory / "identity"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(identity, flags, 0o600)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise WorkflowError("could not write the temporary SSH identity")
            offset += written
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise WorkflowError("temporary SSH identity metadata is unsafe")
    finally:
        os.close(descriptor)
    return identity


def _validate_target_time(value: str) -> None:
    if not TARGET_TIME_RE.fullmatch(value):
        raise WorkflowError("target time must be canonical UTC (YYYY-MM-DDTHH:MM:SSZ)")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise WorkflowError("target time is not a valid UTC timestamp") from exc
    if parsed >= datetime.now(timezone.utc):
        raise WorkflowError("target time must be strictly in the past")


def _remote_command(
    *,
    phase: str,
    target: PatroniNode,
    expected_database_role: str,
    operation_id: str,
    expected_release_sha256: str,
    backup_id: str,
    target_time: str,
) -> str:
    if phase not in {"verify", "restore-drill", "logical-restore-drill"}:
        raise WorkflowError("unreviewed workflow phase")
    if not re.fullmatch(r"[0-9a-f]{32}", operation_id):
        raise WorkflowError("operation ID must be 32 lowercase hexadecimal characters")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_release_sha256):
        raise WorkflowError("expected PITR release digest must be 64 lowercase hex characters")
    command = [
        MANUAL_RUNNER,
        "--phase",
        phase,
        "--project-dir",
        target.project_dir,
        "--compose-file",
        target.compose_file,
        "--operation-id",
        operation_id,
        "--expected-release-sha256",
        expected_release_sha256,
    ]
    if phase == "restore-drill":
        if backup_id:
            if not BACKUP_ID_RE.fullmatch(backup_id):
                raise WorkflowError("backup ID is invalid")
            command.extend(["--backup-id", backup_id])
        if target_time:
            _validate_target_time(target_time)
            command.extend(["--target-time", target_time])
    elif phase == "logical-restore-drill":
        if expected_database_role not in {"primary", "standby"}:
            raise WorkflowError("logical restore target has an invalid database role")
        command.extend(["--expected-database-role", expected_database_role])
    elif expected_database_role:
        raise WorkflowError("database role is valid only for logical-restore-drill")
    if phase != "restore-drill" and (backup_id or target_time):
        raise WorkflowError("backup ID and target time are valid only for restore-drill")
    return "exec " + shlex.join(command)


def _run_checked(
    args: Sequence[str], *, runner: Runner, stdin: str | None = None
) -> str:
    result = runner(args, stdin)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(
            result.stderr,
            end="" if result.stderr.endswith("\n") else "\n",
            file=sys.stderr,
        )
    if result.returncode != 0:
        raise WorkflowError(f"remote PITR operation failed with status {result.returncode}")
    return result.stdout


def _expected_release_sha256(target: PatroniNode) -> str:
    try:
        bundle = json.loads(build_host_release_bundle(target))
    except (TypeError, ValueError) as exc:
        raise WorkflowError("current PITR release bundle is invalid") from exc
    digest = bundle.get("release_sha256") if isinstance(bundle, dict) else None
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise WorkflowError("current PITR release digest is invalid")
    return digest


def _logical_restore_capacity(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    runner: Runner,
) -> tuple[int, int]:
    compose = shlex.join(["docker", "compose", "-f", node.compose_file])
    database_query = (
        'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" '
        '-d "${POSTGRES_DB:-air_conditioners}" -At '
        '-qc "SELECT pg_database_size(current_database())"'
    )
    command = (
        f"cd {shlex.quote(node.project_dir)} && "
        f"live_database_bytes=\"$({compose} exec -T db sh -lc "
        f"{shlex.quote(database_query)})\" && "
        "host_total_bytes=\"$(docker info --format '{{.MemTotal}}')\" && "
        "host_available_kib=\"$(awk '$1 == \"MemAvailable:\" {print $2}' "
        "/proc/meminfo)\" && "
        "printf '%s\\t%s\\t%s\\n' \"${live_database_bytes}\" "
        "\"${host_total_bytes}\" \"${host_available_kib}\""
    )
    result = runner([*ssh_args(node, context), command], None)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "capacity probe failed").strip()
        raise WorkflowError(f"{node.alias}: {detail}")
    fields = result.stdout.strip().split("\t")
    if len(fields) != 3 or any(not value.isdigit() for value in fields):
        raise WorkflowError(f"{node.alias}: logical restore capacity probe is invalid")
    live_database_bytes, host_total_bytes, host_available_kib = map(int, fields)
    if min(live_database_bytes, host_total_bytes, host_available_kib) <= 0:
        raise WorkflowError(f"{node.alias}: logical restore capacity probe is invalid")
    try:
        resources = calculate_resources(
            # The final drill recalculates this with the expanded dump size.
            # Live DB size is the best fail-closed pre-download estimate.
            sql_bytes=live_database_bytes,
            live_database_bytes=live_database_bytes,
            host_total_bytes=host_total_bytes,
        )
    except ResourceSizingError as exc:
        raise WorkflowError(f"{node.alias}: {exc}") from exc
    return host_available_kib * 1024, resources.required_available_bytes


def _select_operation_target(
    *,
    phase: str,
    topology: ClusterTopology,
    context: PinnedSshContext,
    runner: Runner,
) -> tuple[PatroniNode, str]:
    if phase != "logical-restore-drill":
        return topology.primary, ""

    nodes_by_alias = {node.alias: node for node in PATRONI_NODES}
    preferred = nodes_by_alias[LOGICAL_RESTORE_PREFERRED_ALIAS]
    candidates = [
        preferred,
        *(
            node
            for node in PATRONI_NODES
            if node.alias != LOGICAL_RESTORE_PREFERRED_ALIAS
        ),
    ]

    failures: list[str] = []
    for node in candidates:
        role = "primary" if node.alias == topology.primary.alias else "standby"
        try:
            available_bytes, required_bytes = _logical_restore_capacity(
                node=node,
                context=context,
                runner=runner,
            )
        except WorkflowError as exc:
            failures.append(str(exc))
            continue
        print(
            f"[pitr-workflow][capacity] node={node.alias} role={role} "
            f"available_bytes={available_bytes} required_bytes={required_bytes}"
        )
        if available_bytes >= required_bytes:
            return node, role
        failures.append(
            f"{node.alias}: available_bytes={available_bytes} "
            f"required_bytes={required_bytes}"
        )
    raise WorkflowError(
        "no reviewed Patroni node has enough available memory for the logical "
        f"restore preflight ({'; '.join(failures)})"
    )


def _same_topology(before: ClusterTopology, after: ClusterTopology) -> bool:
    return (
        before.primary.alias == after.primary.alias
        and before.standby.alias == after.standby.alias
        and before.system_identifier == after.system_identifier
        and before.timeline == after.timeline
    )


def _detect_pinned_maintenance(
    *,
    context: PinnedSshContext,
    runner: Runner,
):
    nodes_by_alias = {node.alias: node for node in PATRONI_NODES}

    def remote(target: str, source: str) -> subprocess.CompletedProcess[str]:
        if source != REMOTE_PROBE:
            raise WorkflowError("unreviewed maintenance probe source")
        node = nodes_by_alias[target]
        return runner([*ssh_args(node, context), "exec /usr/bin/python3 -I -"], source)

    return detect_window(
        tuple((node.alias, node.alias) for node in PATRONI_NODES),
        runner=remote,
    )


def execute(
    *,
    phase: str,
    backup_id: str,
    target_time: str,
    allow_maintenance_skip: bool = False,
    identity_stream: BinaryIO,
    runner: Runner | None = None,
) -> None:
    actual_runner = runner or _run_subprocess
    payload = bytearray(_read_identity(identity_stream))
    temporary = Path(
        tempfile.mkdtemp(
            prefix="mvn-pitr-workflow-",
            dir=os.environ.get("RUNNER_TEMP") or None,
        )
    )
    try:
        temporary.chmod(0o700)
        identity = _write_identity(temporary, bytes(payload))
        context: PinnedSshContext = create_context(temporary, identity)
        for node in PATRONI_NODES:
            validate_effective_config(node, context)
        maintenance = _detect_pinned_maintenance(
            context=context,
            runner=actual_runner,
        )
        if maintenance.active:
            if phase == "verify" or allow_maintenance_skip:
                print(
                    "[pitr-workflow][maintenance] status=skipped "
                    f"transaction={maintenance.transaction_id} "
                    f"age_seconds={maintenance.age_seconds} nodes=2"
                )
                return
            raise WorkflowError(
                "official Patroni maintenance is active; this manual drill was not skipped"
            )
        before = discover_cluster_topology(context=context, runner=actual_runner)
        target, expected_database_role = _select_operation_target(
            phase=phase,
            topology=before,
            context=context,
            runner=actual_runner,
        )
        operation_id = secrets.token_hex(16)
        expected_release_sha256 = _expected_release_sha256(target)
        command = _remote_command(
            phase=phase,
            target=target,
            expected_database_role=expected_database_role,
            operation_id=operation_id,
            expected_release_sha256=expected_release_sha256,
            backup_id=backup_id,
            target_time=target_time,
        )
        print(
            f"[pitr-workflow][info] selected_primary={before.primary.alias} "
            f"operation_target={target.alias} "
            f"system_identifier={before.system_identifier} timeline={before.timeline}"
        )
        operation_error: BaseException | None = None
        try:
            _run_checked(
                [*ssh_args(target, context), command],
                runner=actual_runner,
            )
        except BaseException as exc:
            operation_error = exc
        try:
            after = discover_cluster_topology(context=context, runner=actual_runner)
            if not _same_topology(before, after):
                raise WorkflowError("Patroni topology changed during the PITR operation")
        except BaseException as topology_error:
            if operation_error is not None:
                raise WorkflowError(
                    f"operation failed: {operation_error}; post-operation topology "
                    f"proof also failed: {topology_error}"
                ) from topology_error
            raise
        if operation_error is not None:
            raise operation_error
        print(
            f"[pitr-workflow][ok] phase={phase} primary={after.primary.alias} "
            f"timeline={after.timeline}"
        )
    finally:
        payload[:] = b"\0" * len(payload)
        for path in (temporary / "config", temporary / "known_hosts", temporary / "identity"):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        temporary.rmdir()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = WorkflowArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("verify", "restore-drill", "logical-restore-drill"),
        required=True,
    )
    parser.add_argument("--backup-id", default="")
    parser.add_argument("--target-time", default="")
    parser.add_argument(
        "--allow-maintenance-skip",
        action="store_true",
        help="Skip a scheduled drill only while both nodes prove official maintenance",
    )
    args = parser.parse_args(argv)
    if args.phase != "restore-drill" and (args.backup_id or args.target_time):
        parser.error("backup/target overrides are valid only for restore-drill")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    os.umask(0o077)

    def interrupt(signum: int, _frame: object) -> None:
        raise KeyboardInterrupt(signum)

    previous_handlers = {
        signum: signal.signal(signum, interrupt)
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
    }
    try:
        execute(
            phase=args.phase,
            backup_id=args.backup_id,
            target_time=args.target_time,
            allow_maintenance_skip=args.allow_maintenance_skip,
            identity_stream=sys.stdin.buffer,
        )
        return 0
    except KeyboardInterrupt:
        print("PITR workflow interrupted", file=sys.stderr)
        return 130
    except (OSError, RuntimeError) as exc:
        print(f"PITR workflow: {exc}", file=sys.stderr)
        return 1
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
