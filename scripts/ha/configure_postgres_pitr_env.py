#!/usr/bin/env python3
"""Atomically split PostgreSQL PITR settings from root-only R2 credentials."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Mapping, Sequence


SECRET_KEYS = (
    "POSTGRES_PITR_CLUSTER",
    "POSTGRES_PITR_S3_BUCKET",
    "POSTGRES_PITR_S3_ENDPOINT_URL",
    "POSTGRES_PITR_S3_REGION",
    "POSTGRES_PITR_S3_ACCESS_KEY_ID",
    "POSTGRES_PITR_S3_SECRET_ACCESS_KEY",
    "POSTGRES_PITR_S3_KEY_PREFIX",
)
PROJECT_KEYS = (
    "POSTGRES_PITR_ARCHIVE_MODE",
    "POSTGRES_PITR_ARCHIVE_TIMEOUT",
)
PITR_KEYS = (*SECRET_KEYS, *PROJECT_KEYS)
REQUIRED_KEYS = (
    "POSTGRES_PITR_CLUSTER",
    "POSTGRES_PITR_S3_BUCKET",
    "POSTGRES_PITR_S3_ENDPOINT_URL",
    "POSTGRES_PITR_S3_ACCESS_KEY_ID",
    "POSTGRES_PITR_S3_SECRET_ACCESS_KEY",
)
PUBLIC_MEDIA_BUCKET_KEYS = {"MEDIA_S3_BUCKET", "PRODUCT_MEDIA_S3_BUCKET"}
LINE_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
BUCKET_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$")
EXPECTED_LOGICAL_PITR_CLUSTER = "mvn-api"
EXPECTED_DESTINATION_FINGERPRINT = (
    "3c6e78da6f79b317f8b62d3f979bb69dba1f2821e473a670be30ec08310f458b"
)
DESTINATION_KEYS = (
    "POSTGRES_PITR_S3_BUCKET",
    "POSTGRES_PITR_S3_ENDPOINT_URL",
    "POSTGRES_PITR_S3_REGION",
    "POSTGRES_PITR_S3_KEY_PREFIX",
)
DEFAULT_SECRETS_FILE = Path("/etc/mvn-postgres-pitr.secrets.env")
DEFAULT_TRANSACTION_ROOT = Path("/var/lib/mvn-postgres-pitr/transactions")
PRODUCTION_PROJECT_DIRS = {Path("/opt/air-api"), Path("/opt/mvn-reserve")}
MAX_ENV_BYTES = 4 * 1024 * 1024
INSTALLED_TRANSACTION_MODULE = Path(
    "/usr/local/sbin/mvn_postgres_pitr_config_transaction.py"
)


def _clean(value: object | None) -> str:
    return str(value or "").strip()


def _parse_dotenv_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_dotenv(
    payload: bytes,
    *,
    label: str,
    allowed_names: set[str] | None = None,
    reject_unknown: bool = False,
) -> dict[str, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{label} is not valid UTF-8") from exc
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE_RE.match(line)
        if not match:
            if reject_unknown:
                raise RuntimeError(f"{label} contains an invalid line")
            continue
        key, raw_value = match.groups()
        if allowed_names is not None and key not in allowed_names:
            if reject_unknown:
                raise RuntimeError(f"{label} contains an unexpected key: {key}")
            continue
        if key in values:
            raise RuntimeError(f"{label} contains duplicate key: {key}")
        values[key] = _parse_dotenv_value(raw_value)
    return values


def _read_fd(
    descriptor: int,
    *,
    label: str,
    limit: int = MAX_ENV_BYTES,
    allow_anonymous: bool = False,
) -> bytes:
    opened = os.fstat(descriptor)
    expected_links = {0} if allow_anonymous else {1}
    if not stat.S_ISREG(opened.st_mode) or opened.st_nlink not in expected_links:
        raise RuntimeError(f"{label} is not a regular file")
    os.lseek(descriptor, 0, os.SEEK_SET)
    payload = bytearray()
    while True:
        chunk = os.read(descriptor, min(131072, limit + 1 - len(payload)))
        if not chunk:
            break
        payload.extend(chunk)
        if len(payload) > limit:
            raise RuntimeError(f"{label} is unexpectedly large")
    finished = os.fstat(descriptor)
    if (
        finished.st_dev,
        finished.st_ino,
        finished.st_size,
        finished.st_mtime_ns,
        finished.st_ctime_ns,
    ) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
        opened.st_ctime_ns,
    ) or len(payload) != opened.st_size:
        raise RuntimeError(f"{label} changed while being read")
    return bytes(payload)


def read_controlled_file(
    path: Path,
    *,
    label: str,
    required: bool,
    expected_uid: int,
    exact_mode: int | None,
) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("required file protection is unavailable")
    try:
        before = path.lstat()
    except FileNotFoundError:
        if required:
            raise RuntimeError(f"{label} is missing")
        return b""
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != expected_uid
        or before.st_nlink != 1
        or (exact_mode is not None and stat.S_IMODE(before.st_mode) != exact_mode)
    ):
        raise RuntimeError(f"{label} metadata is unsafe")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError(f"{label} changed while opening")
        return _read_fd(descriptor, label=label)
    finally:
        os.close(descriptor)


def read_input_file(path: Path, *, expected_uid: int) -> bytes:
    match = re.fullmatch(r"/proc/self/fd/([0-9]+)", str(path))
    if match:
        descriptor = os.dup(int(match.group(1)))
        try:
            metadata = os.fstat(descriptor)
            if metadata.st_uid != expected_uid or stat.S_IMODE(metadata.st_mode) & 0o077:
                raise RuntimeError("PITR input fd metadata is unsafe")
            return _read_fd(
                descriptor,
                label="PITR input fd",
                limit=65536,
                allow_anonymous=True,
            )
        finally:
            os.close(descriptor)
    return read_controlled_file(
        path,
        label="PITR input file",
        required=True,
        expected_uid=expected_uid,
        exact_mode=0o600,
    )


def _arg_value(args: argparse.Namespace, attr: str) -> str:
    return _clean(getattr(args, attr, ""))


def resolve_config(
    *,
    target_values: Mapping[str, str],
    secret_values: Mapping[str, str],
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
            or _clean(secret_values.get(key))
            or _clean(target_values.get(key))
        )
    config["POSTGRES_PITR_S3_REGION"] = config["POSTGRES_PITR_S3_REGION"] or "auto"
    config["POSTGRES_PITR_S3_KEY_PREFIX"] = (
        config["POSTGRES_PITR_S3_KEY_PREFIX"] or "postgres/pitr"
    ).strip("/")
    existing_mode = _clean(target_values.get("POSTGRES_PITR_ARCHIVE_MODE"))
    if args.enable_archive:
        config["POSTGRES_PITR_ARCHIVE_MODE"] = "on"
    elif args.disable_archive:
        config["POSTGRES_PITR_ARCHIVE_MODE"] = "off"
    else:
        config["POSTGRES_PITR_ARCHIVE_MODE"] = (
            existing_mode if existing_mode in {"on", "off"} else "off"
        )
    config["POSTGRES_PITR_ARCHIVE_TIMEOUT"] = (
        config["POSTGRES_PITR_ARCHIVE_TIMEOUT"] or "300s"
    )
    return config


def validate_config(
    config: Mapping[str, str],
    all_values: Mapping[str, str],
    *,
    expected_destination_fingerprint: str = EXPECTED_DESTINATION_FINGERPRINT,
) -> None:
    missing = [key for key in REQUIRED_KEYS if not _clean(config.get(key))]
    if missing:
        raise RuntimeError("Missing required PITR settings: " + ", ".join(missing))
    if config["POSTGRES_PITR_CLUSTER"] != EXPECTED_LOGICAL_PITR_CLUSTER:
        raise RuntimeError("POSTGRES_PITR_CLUSTER must use the reviewed logical namespace")
    bucket = _clean(config["POSTGRES_PITR_S3_BUCKET"])
    if not BUCKET_RE.fullmatch(bucket):
        raise RuntimeError("POSTGRES_PITR_S3_BUCKET is not a canonical private bucket name")
    endpoint = _clean(config["POSTGRES_PITR_S3_ENDPOINT_URL"])
    if (
        not re.fullmatch(
            r"https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.r2\.cloudflarestorage\.com",
            endpoint,
            flags=re.IGNORECASE,
        )
        or ".r2.dev" in endpoint
        or "cdn.mvn.by" in endpoint
    ):
        raise RuntimeError("POSTGRES_PITR_S3_ENDPOINT_URL is not the private R2 S3 API endpoint")
    public_buckets = {
        _clean(all_values.get(key))
        for key in PUBLIC_MEDIA_BUCKET_KEYS
        if _clean(all_values.get(key))
    }
    if bucket in public_buckets:
        raise RuntimeError("POSTGRES_PITR_S3_BUCKET must not reuse the public media bucket")
    destination = "\n".join(config[key] for key in DESTINATION_KEYS) + "\n"
    if hashlib.sha256(destination.encode()).hexdigest() != expected_destination_fingerprint:
        raise RuntimeError("PITR destination does not match the reviewed production archive")
    for key, value in config.items():
        if (
            not value
            or value != value.strip()
            or any(character.isspace() for character in value)
            or any(character in value for character in "#'\"")
        ):
            raise RuntimeError(f"{key} contains an unsafe dotenv value")
    if config["POSTGRES_PITR_ARCHIVE_MODE"] not in {"on", "off"}:
        raise RuntimeError("POSTGRES_PITR_ARCHIVE_MODE is invalid")
    if config["POSTGRES_PITR_ARCHIVE_TIMEOUT"] != "300s":
        raise RuntimeError("POSTGRES_PITR_ARCHIVE_TIMEOUT must be exactly 300s")


def render_env_value(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or any(character.isspace() for character in value)
        or any(character in value for character in "#'\"")
    ):
        raise RuntimeError("PITR dotenv value is unsafe")
    return value


def update_env_text(existing_text: str, updates: Mapping[str, str]) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for line in existing_text.splitlines():
        match = LINE_RE.match(line.strip())
        if match and match.group(1) in SECRET_KEYS:
            continue
        if match and match.group(1) in PROJECT_KEYS:
            key = match.group(1)
            if key in seen:
                raise RuntimeError(f"project env contains duplicate key: {key}")
            lines.append(f"{key}={render_env_value(updates[key])}")
            seen.add(key)
        else:
            lines.append(line)
    missing = [key for key in PROJECT_KEYS if key not in seen]
    if missing:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# PostgreSQL PITR runtime (credentials are root-only)")
        lines.extend(f"{key}={render_env_value(updates[key])}" for key in missing)
    return "\n".join(lines).rstrip() + "\n"


def render_secrets(config: Mapping[str, str]) -> str:
    return "".join(f"{key}={render_env_value(config[key])}\n" for key in SECRET_KEYS)


def validate_sanitized_environment(payload: bytes) -> None:
    project_values = parse_dotenv(payload, label="committed project env")
    if set(SECRET_KEYS).intersection(project_values):
        raise RuntimeError("committed project env still exposes PITR credentials")


def derive_config_transaction_id(
    *,
    root_transaction_id: str,
    node_alias: str,
    stage: str,
    new_env: bytes,
    new_secrets: bytes,
) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", root_transaction_id):
        raise RuntimeError("root PITR transaction ID is invalid")
    if node_alias not in {"mvn-api", "zakup"}:
        raise RuntimeError("PITR transaction node alias is invalid")
    if stage not in {"configure-node", "enable-archive"}:
        raise RuntimeError("PITR configuration transaction stage is invalid")
    material = "\0".join(
        (
            "mvn-pitr-config-v2",
            root_transaction_id,
            node_alias,
            stage,
            hashlib.sha256(new_env).hexdigest(),
            hashlib.sha256(new_secrets).hexdigest(),
        )
    )
    return hashlib.sha256(material.encode("ascii")).hexdigest()[:32]


def load_transaction_module() -> ModuleType:
    candidates = (
        Path(__file__).resolve().with_name("pitr_config_transaction.py"),
        INSTALLED_TRANSACTION_MODULE,
    )
    source = next((candidate for candidate in candidates if candidate.is_file()), None)
    if source is None:
        raise RuntimeError("pinned PITR configuration transaction helper is missing")
    spec = importlib.util.spec_from_file_location(
        "mvn_postgres_pitr_config_transaction", source
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PITR configuration transaction helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default="/opt/air-api")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--secrets-file", default="")
    parser.add_argument("--transaction-root", default="")
    parser.add_argument("--transaction-id", default="")
    parser.add_argument("--root-transaction-id", default="", help=argparse.SUPPRESS)
    parser.add_argument("--transaction-node", default="", help=argparse.SUPPRESS)
    parser.add_argument("--transaction-stage", default="", help=argparse.SUPPRESS)
    parser.add_argument("--input-env-file", default="")
    parser.add_argument("--cluster", default="")
    parser.add_argument("--bucket", default="")
    parser.add_argument("--endpoint-url", default="")
    parser.add_argument("--region", default="")
    parser.add_argument("--access-key-id", default="")
    parser.add_argument("--secret-access-key", default="")
    parser.add_argument("--key-prefix", default="")
    parser.add_argument("--archive-timeout", default="")
    archive = parser.add_mutually_exclusive_group()
    archive.add_argument("--enable-archive", action="store_true")
    archive.add_argument("--disable-archive", action="store_true")
    parser.add_argument(
        "--expected-destination-fingerprint", default="", help=argparse.SUPPRESS
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    expected_uid = os.geteuid()
    project_dir = Path(args.project_dir)
    env_path = Path(args.env_file) if args.env_file else project_dir / ".env"
    if not project_dir.is_absolute() or project_dir.resolve() != project_dir:
        raise RuntimeError("project directory must be an exact absolute path")
    production = project_dir in PRODUCTION_PROJECT_DIRS
    secrets_path = (
        Path(args.secrets_file)
        if args.secrets_file
        else DEFAULT_SECRETS_FILE
        if production
        else project_dir / ".mvn-postgres-pitr.secrets.env"
    )
    transaction_root = (
        Path(args.transaction_root)
        if args.transaction_root
        else DEFAULT_TRANSACTION_ROOT
        if production
        else project_dir / ".mvn-postgres-pitr-transactions"
    )
    if production:
        if expected_uid != 0:
            raise RuntimeError("production PITR configuration requires root")
        if env_path != project_dir / ".env" or secrets_path != DEFAULT_SECRETS_FILE:
            raise RuntimeError("production PITR target paths cannot be overridden")
        if transaction_root != DEFAULT_TRANSACTION_ROOT:
            raise RuntimeError("production PITR transaction root cannot be overridden")
        if args.expected_destination_fingerprint:
            raise RuntimeError("production PITR destination fingerprint cannot be overridden")
    transaction = load_transaction_module()
    transaction.recover_split_transactions(
        transaction_root=transaction_root,
        env_path=env_path,
        secrets_path=secrets_path,
        uid=expected_uid,
        gid=os.getegid(),
        read_controlled_file=read_controlled_file,
        validate_environment=validate_sanitized_environment,
    )
    env_payload = read_controlled_file(
        env_path,
        label="project env",
        required=True,
        expected_uid=expected_uid,
        exact_mode=0o600,
    )
    secrets_exists = secrets_path.exists()
    secrets_payload = read_controlled_file(
        secrets_path,
        label="PITR secrets file",
        required=False,
        expected_uid=expected_uid,
        exact_mode=0o600,
    )
    target_values = parse_dotenv(env_payload, label="project env")
    secret_values = parse_dotenv(
        secrets_payload,
        label="PITR secrets file",
        allowed_names=set(SECRET_KEYS),
        reject_unknown=bool(secrets_payload),
    )
    input_values: dict[str, str] = {}
    if args.input_env_file:
        input_values = parse_dotenv(
            read_input_file(Path(args.input_env_file), expected_uid=expected_uid),
            label="PITR input file",
            allowed_names=set(SECRET_KEYS),
            reject_unknown=True,
        )
    config = resolve_config(
        target_values=target_values,
        secret_values=secret_values,
        input_values=input_values,
        environ=os.environ,
        args=args,
    )
    fingerprint = args.expected_destination_fingerprint or EXPECTED_DESTINATION_FINGERPRINT
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise RuntimeError("reviewed PITR destination fingerprint is invalid")
    merged_values = {**target_values, **secret_values, **input_values, **os.environ}
    validate_config(config, merged_values, expected_destination_fingerprint=fingerprint)
    new_env = update_env_text(env_payload.decode("utf-8"), config).encode("utf-8")
    new_secrets = render_secrets(config).encode("utf-8")
    derived_transaction_fields = (
        args.root_transaction_id,
        args.transaction_node,
        args.transaction_stage,
    )
    if any(derived_transaction_fields) and (
        not all(derived_transaction_fields) or args.transaction_id
    ):
        raise RuntimeError(
            "payload-bound PITR transaction identity requires exactly "
            "root ID, node, and stage"
        )
    if not args.dry_run:
        if all(derived_transaction_fields):
            transaction_id = derive_config_transaction_id(
                root_transaction_id=args.root_transaction_id,
                node_alias=args.transaction_node,
                stage=args.transaction_stage,
                new_env=new_env,
                new_secrets=new_secrets,
            )
        else:
            transaction_id = args.transaction_id or uuid.uuid4().hex
        secrets_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        transaction.commit_split_transaction(
            env_path=env_path,
            secrets_path=secrets_path,
            transaction_root=transaction_root,
            transaction_id=transaction_id,
            old_env=env_payload,
            old_secrets=secrets_payload if secrets_exists else None,
            new_env=new_env,
            new_secrets=new_secrets,
            uid=expected_uid,
            gid=os.getegid(),
            read_controlled_file=read_controlled_file,
            validate_environment=validate_sanitized_environment,
        )
    print(
        json.dumps(
            {
                "archive_mode": config["POSTGRES_PITR_ARCHIVE_MODE"],
                "archive_timeout": config["POSTGRES_PITR_ARCHIVE_TIMEOUT"],
                "cluster": config["POSTGRES_PITR_CLUSTER"],
                "dry_run": args.dry_run,
                "env_path": str(env_path),
                "secrets_path": str(secrets_path),
                "secret_values": "redacted",
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(argv)
    except (OSError, RuntimeError, UnicodeError) as exc:
        print(f"PITR env configure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
