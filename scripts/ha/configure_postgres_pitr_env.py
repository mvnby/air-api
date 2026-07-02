#!/usr/bin/env python3
"""Safely write PostgreSQL PITR settings into a production .env file.

The helper is intentionally conservative:
- it backs up the existing .env before writing;
- it redacts secrets in output;
- it defaults archive_mode to off unless --enable-archive is explicit;
- it refuses to reuse the public media R2 bucket for database PITR.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


PITR_KEYS = [
    "POSTGRES_PITR_CLUSTER",
    "POSTGRES_PITR_S3_BUCKET",
    "POSTGRES_PITR_S3_ENDPOINT_URL",
    "POSTGRES_PITR_S3_REGION",
    "POSTGRES_PITR_S3_ACCESS_KEY_ID",
    "POSTGRES_PITR_S3_SECRET_ACCESS_KEY",
    "POSTGRES_PITR_S3_KEY_PREFIX",
    "POSTGRES_PITR_ARCHIVE_MODE",
    "POSTGRES_PITR_ARCHIVE_TIMEOUT",
]
REQUIRED_KEYS = [
    "POSTGRES_PITR_CLUSTER",
    "POSTGRES_PITR_S3_BUCKET",
    "POSTGRES_PITR_S3_ENDPOINT_URL",
    "POSTGRES_PITR_S3_ACCESS_KEY_ID",
    "POSTGRES_PITR_S3_SECRET_ACCESS_KEY",
]
PUBLIC_MEDIA_BUCKET_KEYS = {
    "MEDIA_S3_BUCKET",
    "PRODUCT_MEDIA_S3_BUCKET",
}
LINE_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
BUCKET_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$")


def _clean(value: object | None) -> str:
    return str(value or "").strip()


def _parse_dotenv_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        match = LINE_RE.match(line.strip())
        if not match:
            continue
        values[match.group(1)] = _parse_dotenv_value(match.group(2))
    return values


def _arg_value(args: argparse.Namespace, attr: str) -> str:
    return _clean(getattr(args, attr, ""))


def resolve_config(
    *,
    target_values: Mapping[str, str],
    input_values: Mapping[str, str],
    environ: Mapping[str, str],
    args: argparse.Namespace,
) -> dict[str, str]:
    mapping = {
        "cluster": "POSTGRES_PITR_CLUSTER",
        "bucket": "POSTGRES_PITR_S3_BUCKET",
        "endpoint_url": "POSTGRES_PITR_S3_ENDPOINT_URL",
        "region": "POSTGRES_PITR_S3_REGION",
        "access_key_id": "POSTGRES_PITR_S3_ACCESS_KEY_ID",
        "secret_access_key": "POSTGRES_PITR_S3_SECRET_ACCESS_KEY",
        "key_prefix": "POSTGRES_PITR_S3_KEY_PREFIX",
        "archive_timeout": "POSTGRES_PITR_ARCHIVE_TIMEOUT",
    }
    config: dict[str, str] = {}
    for attr, key in mapping.items():
        config[key] = (
            _arg_value(args, attr)
            or _clean(environ.get(key))
            or _clean(input_values.get(key))
            or _clean(target_values.get(key))
        )

    config["POSTGRES_PITR_S3_REGION"] = config["POSTGRES_PITR_S3_REGION"] or "auto"
    config["POSTGRES_PITR_S3_KEY_PREFIX"] = (
        config["POSTGRES_PITR_S3_KEY_PREFIX"] or "postgres/pitr"
    ).strip("/")
    config["POSTGRES_PITR_ARCHIVE_MODE"] = "on" if args.enable_archive else "off"
    config["POSTGRES_PITR_ARCHIVE_TIMEOUT"] = (
        config["POSTGRES_PITR_ARCHIVE_TIMEOUT"] or "300s"
    )
    return config


def validate_config(config: Mapping[str, str], all_values: Mapping[str, str]) -> None:
    missing = [key for key in REQUIRED_KEYS if not _clean(config.get(key))]
    if missing:
        raise SystemExit("Missing required PITR settings: " + ", ".join(missing))

    bucket = _clean(config["POSTGRES_PITR_S3_BUCKET"])
    if not BUCKET_RE.match(bucket):
        raise SystemExit(
            "POSTGRES_PITR_S3_BUCKET must be an R2/S3 bucket name with lowercase letters, numbers, and hyphens"
        )

    endpoint = _clean(config["POSTGRES_PITR_S3_ENDPOINT_URL"])
    if not endpoint.startswith("https://") or ".r2.cloudflarestorage.com" not in endpoint:
        raise SystemExit(
            "POSTGRES_PITR_S3_ENDPOINT_URL must look like https://<account-id>.r2.cloudflarestorage.com"
        )

    if ".r2.dev" in endpoint or "cdn.mvn.by" in endpoint:
        raise SystemExit("PITR endpoint must use the private R2 S3 API endpoint, not a public CDN URL")

    public_buckets = {
        _clean(all_values.get(key))
        for key in PUBLIC_MEDIA_BUCKET_KEYS
        if _clean(all_values.get(key))
    }
    if bucket in public_buckets:
        raise SystemExit(
            "POSTGRES_PITR_S3_BUCKET must not reuse the public media bucket"
        )

    for key, value in config.items():
        if "\n" in value or "\r" in value:
            raise SystemExit(f"{key} must be a single-line value")
        if not value or value != value.strip():
            raise SystemExit(f"{key} must not be empty or padded")


def render_env_value(value: str) -> str:
    if not value or any(ch.isspace() for ch in value) or "#" in value or "'" in value or '"' in value:
        raise SystemExit("PITR .env values must not contain whitespace, quotes, or #")
    return value


def update_env_text(existing_text: str, updates: Mapping[str, str]) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for line in existing_text.splitlines():
        match = LINE_RE.match(line.strip())
        if match and match.group(1) in updates:
            key = match.group(1)
            lines.append(f"{key}={render_env_value(updates[key])}")
            seen.add(key)
        else:
            lines.append(line)

    missing = [key for key in PITR_KEYS if key not in seen]
    if missing:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# PostgreSQL PITR")
        for key in missing:
            lines.append(f"{key}={render_env_value(updates[key])}")

    return "\n".join(lines).rstrip() + "\n"


def backup_path(env_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return env_path.with_name(f"{env_path.name}.bak-pitr-{stamp}")


def preserve_owner(path: Path, *, uid: int, gid: int) -> None:
    try:
        os.chown(path, uid, gid)
    except PermissionError:
        pass


def write_env(env_path: Path, content: str, *, dry_run: bool) -> Path | None:
    if dry_run:
        return None

    env_path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    existing_stat = env_path.stat() if env_path.exists() else None
    if env_path.exists():
        backup = backup_path(env_path)
        shutil.copy2(env_path, backup)
        os.chmod(backup, 0o600)
        if existing_stat is not None:
            preserve_owner(backup, uid=existing_stat.st_uid, gid=existing_stat.st_gid)

    fd, tmp_name = tempfile.mkstemp(prefix=f".{env_path.name}.", dir=str(env_path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp_path, 0o600)
        if existing_stat is not None:
            preserve_owner(tmp_path, uid=existing_stat.st_uid, gid=existing_stat.st_gid)
        os.replace(tmp_path, env_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return backup


def print_summary(config: Mapping[str, str], *, env_path: Path, backup: Path | None, dry_run: bool) -> None:
    print(
        {
            "env_path": str(env_path),
            "dry_run": dry_run,
            "backup": str(backup) if backup else None,
            "archive_mode": config["POSTGRES_PITR_ARCHIVE_MODE"],
            "archive_timeout": config["POSTGRES_PITR_ARCHIVE_TIMEOUT"],
            "cluster": config["POSTGRES_PITR_CLUSTER"],
            "bucket": config["POSTGRES_PITR_S3_BUCKET"],
            "endpoint_url": config["POSTGRES_PITR_S3_ENDPOINT_URL"],
            "key_prefix": config["POSTGRES_PITR_S3_KEY_PREFIX"],
            "secret_values": "redacted",
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write private PostgreSQL PITR R2/S3 settings into /opt/air-api/.env safely."
    )
    parser.add_argument("--project-dir", default="/opt/air-api")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--input-env-file", default="")
    parser.add_argument("--cluster", default="")
    parser.add_argument("--bucket", default="")
    parser.add_argument("--endpoint-url", default="")
    parser.add_argument("--region", default="")
    parser.add_argument("--access-key-id", default="")
    parser.add_argument("--secret-access-key", default="")
    parser.add_argument("--key-prefix", default="")
    parser.add_argument("--archive-timeout", default="")
    parser.add_argument("--enable-archive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir)
    env_path = Path(args.env_file) if args.env_file else project_dir / ".env"
    input_path = Path(args.input_env_file) if args.input_env_file else None

    target_values = load_dotenv(env_path)
    input_values = load_dotenv(input_path) if input_path else {}
    merged_values = dict(target_values)
    merged_values.update(input_values)
    merged_values.update({key: value for key, value in os.environ.items() if value})

    config = resolve_config(
        target_values=target_values,
        input_values=input_values,
        environ=os.environ,
        args=args,
    )
    validate_config(config, merged_values)

    existing_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    updated_text = update_env_text(existing_text, config)
    backup = write_env(env_path, updated_text, dry_run=args.dry_run)
    print_summary(config, env_path=env_path, backup=backup, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
