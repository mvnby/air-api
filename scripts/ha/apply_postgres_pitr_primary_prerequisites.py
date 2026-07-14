#!/usr/bin/env python3
"""Apply PostgreSQL PITR primary prerequisites without printing secrets.

The helper probes both reviewed physical Patroni nodes through repository-pinned
SSH host identities, selects the sole writable primary, removes any legacy
disk-based secret file, and runs the bootstrap phase with an in-memory Linux
memfd payload protected by a host lock.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
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

try:
    from scripts.ha.pitr_pinned_ssh import (
        PATRONI_NODES,
        create_context,
        validate_effective_config,
    )
    from scripts.ha.pitr_cluster_topology import ClusterTopology, discover_cluster_topology
    from scripts.ha.pitr_cluster_migration import (
        migrate_cluster,
        validate_transaction_id,
    )
    from scripts.ha.pitr_remote_execution import (
        REMOTE_MAINTENANCE_EXECUTOR,
        REMOTE_SECRET_EXECUTOR,
        run_remote_maintenance_phase,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PATRONI_NODES,
        create_context,
        validate_effective_config,
    )
    from pitr_cluster_topology import (  # type: ignore[no-redef]
        ClusterTopology,
        discover_cluster_topology,
    )
    from pitr_cluster_migration import (  # type: ignore[no-redef]
        migrate_cluster,
        validate_transaction_id,
    )
    from pitr_remote_execution import (  # type: ignore[no-redef]
        REMOTE_MAINTENANCE_EXECUTOR,
        REMOTE_SECRET_EXECUTOR,
        run_remote_maintenance_phase,
    )


DEFAULT_BOOTSTRAP_HELPER = "/usr/local/sbin/mvn-postgres-pitr-bootstrap"
EXPECTED_LOGICAL_PITR_CLUSTER = "mvn-api"
EXPECTED_DESTINATION_FINGERPRINT = (
    "f7dce2229a1d299e9403d4eb639106727676e587b333745c792bff0eacb16f8d"
)
SECRET_PHASES = {"migrate-cluster"}
MAINTENANCE_PHASES = {"restore-drill", "verify"}

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


def subprocess_environment(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    source = environ if environ is not None else os.environ
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "USER", "LOGNAME", "TMPDIR")
    clean = {name: source[name] for name in allowed if source.get(name)}
    clean.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
    clean.setdefault("HOME", str(Path.home()))
    clean.setdefault("LANG", "C")
    clean.setdefault("LC_ALL", "C")
    return clean


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
        env=subprocess_environment(),
    )


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
    if metadata.st_nlink != 1:
        raise RuntimeError(f"{label} must have exactly one filesystem link")
    if metadata.st_uid != os.geteuid():
        raise RuntimeError(f"{label} must be owned by the current user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError(f"{label} must not be accessible by group or other")
    return metadata


def _read_owner_only_file(path: Path, *, label: str, limit: int = 65536) -> str:
    before = _validate_owner_only_regular_file(path, label=label)
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if tuple(getattr(opened, name) for name in fields) != tuple(
            getattr(before, name) for name in fields
        ):
            raise RuntimeError(f"{label} changed while opening")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, min(131072, limit + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > limit:
                raise RuntimeError(f"{label} is too large")
        after = os.fstat(descriptor)
        if tuple(getattr(after, name) for name in fields) != tuple(
            getattr(opened, name) for name in fields
        ):
            raise RuntimeError(f"{label} changed while reading")
    finally:
        os.close(descriptor)
    try:
        return bytes(payload).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{label} must be UTF-8") from exc


def load_env_file(
    path: Path, *, allowed_names: set[str] = PITR_ENV_NAMES
) -> dict[str, str]:
    parsed_values: dict[str, str] = {}
    payload = _read_owner_only_file(path, label="PITR env file")
    for line in payload.splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in allowed_names:
            continue
        if key in parsed_values:
            raise RuntimeError(f"PITR env file contains duplicate key: {key}")
        parsed_values[key] = value

    log("ok", f"loaded env file: {path} keys={len(parsed_values)}")
    return parsed_values


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
    source = environ if environ is not None else os.environ
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
    if config.cluster != EXPECTED_LOGICAL_PITR_CLUSTER:
        raise RuntimeError(
            "POSTGRES_PITR_CLUSTER must use the reviewed logical namespace "
            f"({EXPECTED_LOGICAL_PITR_CLUSTER})"
        )

    if not BUCKET_RE.match(config.bucket):
        raise RuntimeError(
            "POSTGRES_PITR_S3_BUCKET must be an R2/S3 bucket name with lowercase letters, numbers, and hyphens"
        )
    if not re.fullmatch(
        r"https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.r2\.cloudflarestorage\.com",
        config.endpoint_url,
        flags=re.IGNORECASE,
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
    destination = "\n".join(
        (
            config.bucket,
            config.endpoint_url,
            config.region,
            config.key_prefix,
        )
    ) + "\n"
    if hashlib.sha256(destination.encode()).hexdigest() != EXPECTED_DESTINATION_FINGERPRINT:
        raise RuntimeError("PITR destination does not match the reviewed production archive")


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
        choices=tuple(sorted(SECRET_PHASES | MAINTENANCE_PHASES)),
        default="migrate-cluster",
        help=(
            "Use preflight first. Maintenance phases run through the same pinned "
            "primary discovery and canonical node mapping."
        ),
    )
    parser.add_argument(
        "--transaction-id",
        default=os.environ.get("PITR_TRANSACTION_ID") or "",
        help=(
            "Required 32-character lowercase hexadecimal cluster transaction ID "
            "for every live or dry-run mutation phase. Reuse it to resume."
        ),
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


def _require_same_topology(
    before: ClusterTopology,
    after: ClusterTopology,
    *,
    stage: str,
) -> None:
    fields = (
        ("system_identifier", before.system_identifier, after.system_identifier),
        ("timeline", before.timeline, after.timeline),
        ("primary", before.primary.alias, after.primary.alias),
        ("standby", before.standby.alias, after.standby.alias),
    )
    drift = [name for name, expected, actual in fields if actual != expected]
    if drift:
        raise RuntimeError(f"topology drift after {stage}: " + ", ".join(drift))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        transaction_id = ""
        if not args.probe_only:
            transaction_id = validate_transaction_id(args.transaction_id)
        secret_phase = args.phase in SECRET_PHASES
        config: PitrInput | None = None
        if not args.probe_only and secret_phase:
            input_environment = dict(os.environ)
            if args.env_file:
                file_values = load_env_file(Path(args.env_file))
                for key, value in file_values.items():
                    if key in input_environment and input_environment[key] != value:
                        raise RuntimeError(
                            f"ambient environment conflicts with PITR env file key: {key}"
                        )
                    input_environment.setdefault(key, value)
            config = collect_inputs(
                environ=input_environment,
                no_prompt=args.no_prompt,
            )
            log("info", f"phase={args.phase}")
            log("info", "PITR R2 access key values will not be printed")
        elif not args.probe_only:
            if args.env_file:
                raise RuntimeError("--env-file is not accepted for maintenance phases")
            log("info", f"maintenance phase={args.phase}")

        if args.dry_run:
            if config is not None:
                log("dry-run", "would send this redacted env to the primary:")
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
            if args.probe_only:
                topology = discover_cluster_topology(
                    context=context,
                    runner=_run_subprocess,
                )
                log("ok", f"selected Patroni primary: {topology.primary.alias}")
                log("ok", "pinned SSH and Patroni topology probe passed")
                return 0
            if args.phase == "migrate-cluster":
                if config is None:
                    raise RuntimeError("PITR input was not loaded")
                result = migrate_cluster(
                    context=context,
                    env_text=render_env(config),
                    transaction_id=transaction_id,
                    runner=_run_subprocess,
                    bootstrap_helper=DEFAULT_BOOTSTRAP_HELPER,
                )
                log(
                    "ok",
                    "cluster PITR migration passed: "
                    f"primary={result.primary_alias} standby={result.standby_alias} "
                    f"timeline={result.timeline}",
                )
                return 0
            topology = discover_cluster_topology(
                context=context,
                runner=_run_subprocess,
            )
            primary = topology.primary
            log("ok", f"selected Patroni primary: {primary.alias}")
            action_error: BaseException | None = None
            try:
                run_remote_maintenance_phase(
                    node=primary,
                    context=context,
                    bootstrap_helper=DEFAULT_BOOTSTRAP_HELPER,
                    phase=args.phase,
                    transaction_id=transaction_id,
                    runner=_run_subprocess,
                )
            except BaseException as exc:
                action_error = exc
            try:
                after = discover_cluster_topology(
                    context=context,
                    runner=_run_subprocess,
                )
                _require_same_topology(topology, after, stage=args.phase)
            except BaseException as topology_error:
                if action_error is not None:
                    raise RuntimeError(
                        f"{args.phase} failed: {action_error}; topology proof after "
                        f"the attempted operation also failed: {topology_error}"
                    ) from topology_error
                raise
            if action_error is not None:
                raise action_error
            log("ok", f"remote PITR phase passed: {args.phase}")
        return 0
    except RuntimeError as exc:
        log("fail", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
