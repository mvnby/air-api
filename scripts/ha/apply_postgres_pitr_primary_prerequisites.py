#!/usr/bin/env python3
"""Apply PostgreSQL PITR primary prerequisites without printing secrets.

The helper probes both reviewed physical Patroni nodes through repository-pinned
SSH host identities, selects the sole writable primary, uploads a temporary
root-only env file there, runs a safe bootstrap phase, and removes the temporary
file even when upload or bootstrap fails.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit

try:
    from scripts.ha.pitr_pinned_ssh import (
        PATRONI_NODES,
        PatroniNode,
        PinnedSshContext,
        create_context,
        ssh_args,
        validate_effective_config,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PATRONI_NODES,
        PatroniNode,
        PinnedSshContext,
        create_context,
        ssh_args,
        validate_effective_config,
    )


DEFAULT_REMOTE_ENV_FILE = "/root/mvn-postgres-pitr.env"
DEFAULT_BOOTSTRAP_HELPER = "/usr/local/sbin/mvn-postgres-pitr-bootstrap"

BUCKET_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$")
PITR_ENV_NAMES = {
    "POSTGRES_PITR_CLUSTER",
    "POSTGRES_PITR_S3_BUCKET",
    "POSTGRES_PITR_S3_ENDPOINT_URL",
    "POSTGRES_PITR_S3_REGION",
    "POSTGRES_PITR_S3_ACCESS_KEY_ID",
    "POSTGRES_PITR_S3_SECRET_ACCESS_KEY",
    "POSTGRES_PITR_S3_KEY_PREFIX",
}

Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class PitrInput:
    cluster: str
    bucket: str
    endpoint_url: str
    region: str
    access_key_id: str
    secret_access_key: str
    key_prefix: str


def log(stage: str, message: str) -> None:
    print(f"[ha-pitr-setup][{stage}] {message}")


def _run_subprocess(args: Sequence[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def run_checked(
    args: Sequence[str],
    *,
    stdin: str | None = None,
    runner: Runner | None = None,
    print_output: bool = True,
) -> str:
    actual_runner = runner or _run_subprocess
    result = actual_runner(args, stdin)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(output or f"command failed: {' '.join(args)}")
    output = result.stdout.strip()
    if output and print_output:
        print(output)
    return output


def _clean(value: object | None) -> str:
    return str(value or "").strip()


def _env(name: str, environ: Mapping[str, str]) -> str:
    return _clean(environ.get(name))


def _parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, raw_value = line.split("=", 1)
    key = key.strip().removeprefix("export ").strip()
    if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        return None
    raw_value = raw_value.strip()
    if raw_value and raw_value[0] in {"'", '"'}:
        try:
            parts = shlex.split(f"{key}={raw_value}", posix=True)
        except ValueError:
            parts = []
        if parts and "=" in parts[0]:
            return key, parts[0].split("=", 1)[1]
    if " #" in raw_value:
        raw_value = raw_value.split(" #", 1)[0].rstrip()
    return key, raw_value


def _validate_owner_only_regular_file(path: Path, *, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} not found: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"{label} must be a regular non-symlink file")
    if metadata.st_uid != os.geteuid():
        raise RuntimeError(f"{label} must be owned by the current user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError(f"{label} must not be accessible by group or other")
    return metadata


def load_env_file(path: Path, *, allowed_names: set[str] = PITR_ENV_NAMES) -> None:
    _validate_owner_only_regular_file(path, label="PITR env file")
    loaded = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in allowed_names:
            continue
        if key not in os.environ:
            os.environ[key] = value
            loaded += 1
    log("ok", f"loaded env file: {path} keys={loaded}")


def _prompt(name: str, *, secret: bool, no_prompt: bool) -> str:
    if no_prompt:
        return ""
    if not sys.stdin.isatty():
        return ""
    if secret:
        return getpass.getpass(f"{name}: ").strip()
    return input(f"{name}: ").strip()


def _value(
    *,
    environ: Mapping[str, str],
    name: str,
    default: str = "",
    secret: bool = False,
    no_prompt: bool,
) -> str:
    return _env(name, environ) or default or _prompt(name, secret=secret, no_prompt=no_prompt)


def collect_inputs(
    *,
    environ: Mapping[str, str] | None = None,
    no_prompt: bool = False,
) -> PitrInput:
    source = environ or os.environ
    config = PitrInput(
        cluster=_value(
            environ=source,
            name="POSTGRES_PITR_CLUSTER",
            default="mvn-api",
            no_prompt=no_prompt,
        ).strip("/"),
        bucket=_value(environ=source, name="POSTGRES_PITR_S3_BUCKET", no_prompt=no_prompt),
        endpoint_url=_value(environ=source, name="POSTGRES_PITR_S3_ENDPOINT_URL", no_prompt=no_prompt),
        region=_value(
            environ=source,
            name="POSTGRES_PITR_S3_REGION",
            default="auto",
            no_prompt=no_prompt,
        ),
        access_key_id=_value(
            environ=source,
            name="POSTGRES_PITR_S3_ACCESS_KEY_ID",
            secret=True,
            no_prompt=no_prompt,
        ),
        secret_access_key=_value(
            environ=source,
            name="POSTGRES_PITR_S3_SECRET_ACCESS_KEY",
            secret=True,
            no_prompt=no_prompt,
        ),
        key_prefix=_value(
            environ=source,
            name="POSTGRES_PITR_S3_KEY_PREFIX",
            default="postgres/pitr",
            no_prompt=no_prompt,
        ).strip("/"),
    )
    validate_input(config)
    return config


def validate_input(config: PitrInput) -> None:
    missing = [
        name
        for name, value in (
            ("POSTGRES_PITR_CLUSTER", config.cluster),
            ("POSTGRES_PITR_S3_BUCKET", config.bucket),
            ("POSTGRES_PITR_S3_ENDPOINT_URL", config.endpoint_url),
            ("POSTGRES_PITR_S3_ACCESS_KEY_ID", config.access_key_id),
            ("POSTGRES_PITR_S3_SECRET_ACCESS_KEY", config.secret_access_key),
            ("POSTGRES_PITR_S3_KEY_PREFIX", config.key_prefix),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("missing required PITR settings: " + ", ".join(missing))

    if not BUCKET_RE.match(config.bucket):
        raise RuntimeError(
            "POSTGRES_PITR_S3_BUCKET must be an R2/S3 bucket name with lowercase letters, numbers, and hyphens"
        )
    try:
        endpoint = urlsplit(config.endpoint_url)
        endpoint_port = endpoint.port
    except ValueError as exc:
        raise RuntimeError("POSTGRES_PITR_S3_ENDPOINT_URL is invalid") from exc
    endpoint_host = endpoint.hostname or ""
    valid_endpoint_host = re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.r2\.cloudflarestorage\.com",
        endpoint_host,
        flags=re.IGNORECASE,
    )
    if (
        endpoint.scheme.lower() != "https"
        or valid_endpoint_host is None
        or endpoint.username is not None
        or endpoint.password is not None
        or endpoint_port not in {None, 443}
        or endpoint.path not in {"", "/"}
        or endpoint.query
        or endpoint.fragment
    ):
        raise RuntimeError(
            "POSTGRES_PITR_S3_ENDPOINT_URL must look like https://<account-id>.r2.cloudflarestorage.com"
        )

    for name, value in (
        ("POSTGRES_PITR_CLUSTER", config.cluster),
        ("POSTGRES_PITR_S3_BUCKET", config.bucket),
        ("POSTGRES_PITR_S3_ENDPOINT_URL", config.endpoint_url),
        ("POSTGRES_PITR_S3_REGION", config.region),
        ("POSTGRES_PITR_S3_ACCESS_KEY_ID", config.access_key_id),
        ("POSTGRES_PITR_S3_SECRET_ACCESS_KEY", config.secret_access_key),
        ("POSTGRES_PITR_S3_KEY_PREFIX", config.key_prefix),
    ):
        if "\n" in value or "\r" in value:
            raise RuntimeError(f"{name} must be a single-line value")
        if value != value.strip() or any(ch.isspace() for ch in value) or "#" in value or "'" in value or '"' in value:
            raise RuntimeError(f"{name} must not contain whitespace, quotes, or #")


def render_env(config: PitrInput, *, redact: bool = False) -> str:
    access_key_id = "redacted" if redact else config.access_key_id
    secret_access_key = "redacted" if redact else config.secret_access_key
    return "\n".join(
        [
            f"POSTGRES_PITR_CLUSTER={config.cluster}",
            f"POSTGRES_PITR_S3_BUCKET={config.bucket}",
            f"POSTGRES_PITR_S3_ENDPOINT_URL={config.endpoint_url}",
            f"POSTGRES_PITR_S3_REGION={config.region}",
            f"POSTGRES_PITR_S3_ACCESS_KEY_ID={access_key_id}",
            f"POSTGRES_PITR_S3_SECRET_ACCESS_KEY={secret_access_key}",
            f"POSTGRES_PITR_S3_KEY_PREFIX={config.key_prefix}",
            "",
        ]
    )


def validate_identity_file(raw_path: str) -> Path:
    if not raw_path.strip():
        raise RuntimeError(
            "--identity-file or HA_SSH_IDENTITY_FILE is required for a live apply"
        )
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise RuntimeError("SSH identity file must use an absolute path")
    _validate_owner_only_regular_file(path, label="SSH identity file")
    return path


def _patroni_role(payload: object, node: PatroniNode) -> str:
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"{node.alias}: invalid Patroni response")
    state = _clean(payload.get("state")).lower()
    role = _clean(payload.get("role")).lower()
    patroni = payload.get("patroni")
    nested_name = patroni.get("name") if isinstance(patroni, Mapping) else ""
    actual_name = _clean(payload.get("name") or nested_name)
    unsafe_flags = {
        "pending_restart": "pending restart",
        "pause": "cluster pause",
        "cluster_unlocked": "missing DCS leader lock",
        "failsafe_mode_is_active": "DCS failsafe mode",
    }
    if state != "running":
        raise RuntimeError(f"{node.alias}: Patroni is not running")
    if actual_name != node.alias:
        raise RuntimeError(
            f"{node.alias}: Patroni node identity is {actual_name or '<empty>'}, expected {node.alias}"
        )
    for field, description in unsafe_flags.items():
        if payload.get(field) is True:
            raise RuntimeError(f"{node.alias}: Patroni reports {description}")
    if role in {"leader", "master", "primary"}:
        return "primary"
    if role in {"replica", "standby"}:
        return "standby"
    raise RuntimeError(f"{node.alias}: unsupported Patroni role: {role or '<empty>'}")


def discover_primary(
    *,
    context: PinnedSshContext,
    nodes: Sequence[PatroniNode] = PATRONI_NODES,
    runner: Runner | None = None,
) -> PatroniNode:
    roles: dict[str, str] = {}
    for node in nodes:
        output = run_checked(
            [
                *ssh_args(node, context),
                "curl -fsS --max-time 5 http://127.0.0.1:8008/patroni",
            ],
            runner=runner,
            print_output=False,
        )
        try:
            payload = json.loads(output)
        except ValueError as exc:
            raise RuntimeError(f"{node.alias}: invalid Patroni JSON") from exc
        roles[node.alias] = _patroni_role(payload, node)
        log("probe", f"{node.alias} role={roles[node.alias]}")
    primaries = [node for node in nodes if roles.get(node.alias) == "primary"]
    standbys = [node for node in nodes if roles.get(node.alias) == "standby"]
    if len(primaries) != 1 or len(standbys) != len(nodes) - 1:
        rendered = " ".join(
            f"{node.alias}={roles.get(node.alias, 'unknown')}" for node in nodes
        )
        raise RuntimeError(f"unsafe Patroni topology: {rendered}")
    primary = primaries[0]
    log("ok", f"selected Patroni primary: {primary.alias}")
    return primary


REMOTE_SECRET_EXECUTOR = r"""
import fcntl
import os
import stat
import subprocess
import sys

MAX_PAYLOAD_BYTES = 65536
LOCK_PATH = "/run/lock/mvn-postgres-pitr-prerequisites.lock"


def fail(message, status=70):
    print(f"pitr secret executor: {message}", file=sys.stderr)
    return status


def main():
    if len(sys.argv) != 5:
        return fail("invalid invocation", 64)
    if os.geteuid() != 0:
        return fail("root execution is required", 77)
    if not hasattr(os, "memfd_create") or not hasattr(os, "O_NOFOLLOW"):
        return fail("required Linux secret transport is unavailable")
    bootstrap_helper, phase, project_dir, compose_file = sys.argv[1:]
    os.umask(0o077)
    lock_flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    lock_fd = os.open(LOCK_PATH, lock_flags, 0o600)
    try:
        lock_metadata = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_uid != os.geteuid()
            or lock_metadata.st_nlink != 1
        ):
            return fail("lock file metadata is unsafe")
        os.fchmod(lock_fd, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return fail("another PITR prerequisite apply is active", 75)
        payload = bytearray(sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1))
        if not payload or len(payload) > MAX_PAYLOAD_BYTES:
            return fail("secret payload size is invalid", 65)
        secret_fd = os.memfd_create("mvn-postgres-pitr-env", flags=0)
        payload_view = memoryview(payload)
        try:
            os.fchmod(secret_fd, 0o600)
            offset = 0
            while offset < len(payload_view):
                written = os.write(secret_fd, payload_view[offset:])
                if written <= 0:
                    return fail("could not stage secret payload")
                offset += written
            os.lseek(secret_fd, 0, os.SEEK_SET)
            environment = os.environ.copy()
            for name in (
                "BASH_ENV",
                "CDPATH",
                "ENV",
                "LD_AUDIT",
                "LD_LIBRARY_PATH",
                "LD_PRELOAD",
                "PYTHONHOME",
                "PYTHONINSPECT",
                "PYTHONPATH",
                "PYTHONSTARTUP",
            ):
                environment.pop(name, None)
            environment.update(
                {
                    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    "PROJECT_DIR": project_dir,
                    "COMPOSE_FILE": compose_file,
                    "ENV_INPUT_FILE": f"/proc/self/fd/{secret_fd}",
                }
            )
            result = subprocess.run(
                [bootstrap_helper, phase],
                env=environment,
                pass_fds=(secret_fd, lock_fd),
                check=False,
            )
            return result.returncode
        finally:
            payload_view[:] = b"\0" * len(payload_view)
            payload_view.release()
            os.close(secret_fd)
    finally:
        os.close(lock_fd)


raise SystemExit(main())
""".strip()


def run_remote_secret_phase(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    env_text: str,
    bootstrap_helper: str,
    phase: str,
    runner: Runner | None = None,
) -> None:
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
        ]
    )
    run_checked(
        [*ssh_args(node, context), command],
        stdin=env_text,
        runner=runner,
    )
    log("ok", f"remote PITR phase passed: {phase}")


def cleanup_remote_env(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    remote_env_file: str,
    runner: Runner | None = None,
) -> None:
    remote_file = shlex.quote(remote_env_file)
    run_checked(
        [*ssh_args(node, context), f"rm -f -- {remote_file}"],
        runner=runner,
    )
    log("ok", f"temporary PITR env absent on {node.alias}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare current PostgreSQL primary for private R2/S3 PITR without printing secrets."
    )
    parser.add_argument(
        "--identity-file",
        default=os.environ.get("HA_SSH_IDENTITY_FILE") or "",
        help="Owner-only SSH private key used with repository-pinned physical host identities.",
    )
    parser.add_argument(
        "--env-file",
        default=os.environ.get("HA_ENV_FILE") or "",
        help="Optional dotenv-style file to load before reading PITR inputs.",
    )
    parser.add_argument(
        "--phase",
        choices=("preflight", "bootstrap-before-maintenance"),
        default="preflight",
        help="Use preflight first. bootstrap-before-maintenance writes PITR env and uploads the first basebackup.",
    )
    execution_mode = parser.add_mutually_exclusive_group()
    execution_mode.add_argument("--dry-run", action="store_true")
    execution_mode.add_argument(
        "--probe-only",
        action="store_true",
        help="Verify both pinned SSH identities and the sole Patroni primary without reading PITR secrets.",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not prompt for missing PITR values; fail instead.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        config: PitrInput | None = None
        if not args.probe_only:
            if args.env_file:
                load_env_file(Path(args.env_file))
            config = collect_inputs(no_prompt=args.no_prompt)
            log("info", f"phase={args.phase}")
            log("info", "PITR R2 access key values will not be printed")

        if args.dry_run and config is not None:
            log("dry-run", "would upload this redacted env to the primary:")
            print(render_env(config, redact=True).rstrip())
            aliases = ", ".join(node.alias for node in PATRONI_NODES)
            log("dry-run", f"would probe pinned Patroni nodes: {aliases}")
            log(
                "dry-run",
                f"would run {DEFAULT_BOOTSTRAP_HELPER} {args.phase} on the sole primary",
            )
            return 0

        identity_file = validate_identity_file(args.identity_file)
        with tempfile.TemporaryDirectory(prefix="mvn-pitr-pinned-ssh-") as temporary_dir:
            context = create_context(Path(temporary_dir), identity_file)
            for node in PATRONI_NODES:
                validate_effective_config(node, context)
            primary = discover_primary(context=context)
            if args.probe_only:
                log("ok", "pinned SSH and Patroni primary probe passed")
                return 0
            if config is None:
                raise RuntimeError("PITR input was not loaded")
            if config.cluster != primary.alias:
                raise RuntimeError(
                    "POSTGRES_PITR_CLUSTER must match the selected Patroni primary "
                    f"({primary.alias})"
                )
            for node in PATRONI_NODES:
                cleanup_remote_env(
                    node=node,
                    context=context,
                    remote_env_file=DEFAULT_REMOTE_ENV_FILE,
                )
            env_text = render_env(config)
            run_remote_secret_phase(
                node=primary,
                context=context,
                env_text=env_text,
                bootstrap_helper=DEFAULT_BOOTSTRAP_HELPER,
                phase=args.phase,
            )
        return 0
    except RuntimeError as exc:
        log("fail", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
