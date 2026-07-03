#!/usr/bin/env python3
"""Apply PostgreSQL PITR primary prerequisites without printing secrets.

This helper collects private R2/S3 PITR settings locally, uploads a temporary
root-only env file to the current primary over SSH, runs a safe pre-maintenance
bootstrap phase, and removes the temporary env file from the host.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


DEFAULT_PRIMARY_HOST = "mvn-api"
DEFAULT_PROJECT_DIR = "/opt/air-api"
DEFAULT_COMPOSE_FILE = "docker-compose.prod.yml"
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


def run_checked(args: Sequence[str], *, stdin: str | None = None, runner: Runner | None = None) -> str:
    actual_runner = runner or _run_subprocess
    result = actual_runner(args, stdin)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(output or f"command failed: {' '.join(args)}")
    output = result.stdout.strip()
    if output:
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


def load_env_file(path: Path, *, allowed_names: set[str] = PITR_ENV_NAMES) -> None:
    if not path.exists():
        raise RuntimeError(f"env file not found: {path}")
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
    if not config.endpoint_url.startswith("https://") or ".r2.cloudflarestorage.com" not in config.endpoint_url:
        raise RuntimeError(
            "POSTGRES_PITR_S3_ENDPOINT_URL must look like https://<account-id>.r2.cloudflarestorage.com"
        )
    if ".r2.dev" in config.endpoint_url or "cdn.mvn.by" in config.endpoint_url:
        raise RuntimeError("PITR endpoint must use the private R2 S3 API endpoint, not a public CDN URL")

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


def upload_remote_env(
    *,
    ssh_host: str,
    remote_env_file: str,
    env_text: str,
    runner: Runner | None = None,
) -> None:
    remote_file = shlex.quote(remote_env_file)
    run_checked(
        ["ssh", ssh_host, f"umask 077; cat > {remote_file}; chmod 600 {remote_file}"],
        stdin=env_text,
        runner=runner,
    )
    log("ok", f"temporary PITR env uploaded to {ssh_host}:{remote_env_file}")


def run_remote_phase(
    *,
    ssh_host: str,
    remote_env_file: str,
    bootstrap_helper: str,
    project_dir: str,
    compose_file: str,
    phase: str,
    runner: Runner | None = None,
) -> None:
    remote_file = shlex.quote(remote_env_file)
    command = " ".join(
        [
            f"PROJECT_DIR={shlex.quote(project_dir)}",
            f"COMPOSE_FILE={shlex.quote(compose_file)}",
            f"ENV_INPUT_FILE={remote_file}",
            shlex.quote(bootstrap_helper),
            shlex.quote(phase),
            ";",
            "status=$?",
            ";",
            "rm -f",
            remote_file,
            ";",
            "exit ${status}",
        ]
    )
    run_checked(["ssh", ssh_host, command], runner=runner)
    log("ok", f"remote PITR phase passed: {phase}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare current PostgreSQL primary for private R2/S3 PITR without printing secrets."
    )
    parser.add_argument("--ssh-host", default=DEFAULT_PRIMARY_HOST)
    parser.add_argument("--project-dir", default=DEFAULT_PROJECT_DIR)
    parser.add_argument("--compose-file", default=DEFAULT_COMPOSE_FILE)
    parser.add_argument("--remote-env-file", default=DEFAULT_REMOTE_ENV_FILE)
    parser.add_argument("--bootstrap-helper", default=DEFAULT_BOOTSTRAP_HELPER)
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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not prompt for missing PITR values; fail instead.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.env_file:
            load_env_file(Path(args.env_file))
        config = collect_inputs(no_prompt=args.no_prompt)
        log("info", f"ssh_host={args.ssh_host} project_dir={args.project_dir} compose_file={args.compose_file}")
        log("info", f"phase={args.phase}")
        log("info", "PITR R2 access key values will not be printed")

        if args.dry_run:
            log("dry-run", "would upload this redacted env to the primary:")
            print(render_env(config, redact=True).rstrip())
            log("dry-run", f"would run {args.bootstrap_helper} {args.phase} on {args.ssh_host}")
            return 0

        env_text = render_env(config)
        upload_remote_env(
            ssh_host=args.ssh_host,
            remote_env_file=args.remote_env_file,
            env_text=env_text,
        )
        run_remote_phase(
            ssh_host=args.ssh_host,
            remote_env_file=args.remote_env_file,
            bootstrap_helper=args.bootstrap_helper,
            project_dir=args.project_dir,
            compose_file=args.compose_file,
            phase=args.phase,
        )
        return 0
    except RuntimeError as exc:
        log("fail", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
