#!/usr/bin/env python3
"""Upload PostgreSQL PITR artifacts to a private S3-compatible bucket.

This is intended to run from the backend image, which already includes boto3.
It deliberately requires POSTGRES_PITR_* variables and does not fall back to
public product-media R2 credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

WAL_NAME_RE = re.compile(
    r"^(?:[0-9A-F]{24}|[0-9A-F]{24}\.[0-9A-F]{8}\.backup|[0-9A-F]{8}\.history)$"
)


@dataclass(frozen=True)
class PitrS3Config:
    bucket: str
    endpoint_url: str
    region: str
    access_key_id: str
    secret_access_key: str
    key_prefix: str
    cluster: str


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_config() -> PitrS3Config:
    config = PitrS3Config(
        bucket=_env("POSTGRES_PITR_S3_BUCKET"),
        endpoint_url=_env("POSTGRES_PITR_S3_ENDPOINT_URL"),
        region=_env("POSTGRES_PITR_S3_REGION", "auto"),
        access_key_id=_env("POSTGRES_PITR_S3_ACCESS_KEY_ID"),
        secret_access_key=_env("POSTGRES_PITR_S3_SECRET_ACCESS_KEY"),
        key_prefix=_env("POSTGRES_PITR_S3_KEY_PREFIX", "postgres/pitr").strip("/"),
        cluster=_env("POSTGRES_PITR_CLUSTER").strip("/"),
    )
    missing = [
        name
        for name, value in (
            ("POSTGRES_PITR_S3_BUCKET", config.bucket),
            ("POSTGRES_PITR_S3_ENDPOINT_URL", config.endpoint_url),
            ("POSTGRES_PITR_S3_ACCESS_KEY_ID", config.access_key_id),
            ("POSTGRES_PITR_S3_SECRET_ACCESS_KEY", config.secret_access_key),
            ("POSTGRES_PITR_CLUSTER", config.cluster),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing private PostgreSQL PITR S3 settings: " + ", ".join(missing)
        )
    return config


def build_client(config: PitrS3Config):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - dependency check
        raise SystemExit("boto3/botocore are required for PITR uploads") from exc

    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        region_name=config.region,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        config=Config(signature_version="s3v4"),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_wal_files(archive_dir: Path) -> Iterable[Path]:
    for path in sorted(archive_dir.iterdir()):
        if not path.is_file():
            continue
        if WAL_NAME_RE.match(path.name):
            yield path


def wal_key(config: PitrS3Config, filename: str) -> str:
    timeline = filename[:8]
    return f"{config.key_prefix}/{config.cluster}/wal/{timeline}/{filename}"


def basebackup_key(config: PitrS3Config, backup_id: str, filename: str) -> str:
    return f"{config.key_prefix}/{config.cluster}/basebackups/{backup_id}/{filename}"


def upload_file(client, config: PitrS3Config, source: Path, key: str, dry_run: bool) -> None:
    if dry_run:
        print(json.dumps({"action": "dry_run_upload", "key": key, "path": str(source)}))
        return

    client.upload_file(
        str(source),
        config.bucket,
        key,
        ExtraArgs={
            "ContentType": "application/octet-stream",
            "CacheControl": "private, max-age=0, no-store",
            "Metadata": {
                "sha256": sha256_file(source),
                "uploaded-by": "mvn-postgres-pitr",
            },
        },
    )
    client.head_object(Bucket=config.bucket, Key=key)


def upload_wal(args: argparse.Namespace) -> int:
    config = load_config()
    archive_dir = Path(args.archive_dir)
    if not archive_dir.is_dir():
        raise SystemExit(f"WAL archive dir does not exist: {archive_dir}")

    client = build_client(config)
    uploaded = 0
    for path in iter_wal_files(archive_dir):
        key = wal_key(config, path.name)
        upload_file(client, config, path, key, args.dry_run)
        uploaded += 1
        print(
            json.dumps(
                {
                    "action": "uploaded_wal" if not args.dry_run else "planned_wal",
                    "filename": path.name,
                    "key": key,
                    "size_bytes": path.stat().st_size,
                },
                sort_keys=True,
            )
        )
        if args.delete_after_upload and not args.dry_run:
            path.unlink()

    print(json.dumps({"kind": "wal", "count": uploaded}, sort_keys=True))
    return 0


def iter_basebackup_files(source_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(source_dir.iterdir())
        if path.is_file() and not path.name.startswith(".")
    ]


def upload_basebackup(args: argparse.Namespace) -> int:
    config = load_config()
    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        raise SystemExit(f"Basebackup dir does not exist: {source_dir}")

    backup_id = args.backup_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    files = iter_basebackup_files(source_dir)
    if not files:
        raise SystemExit(f"No basebackup files found in {source_dir}")

    client = build_client(config)
    manifest = {
        "backup_id": backup_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cluster": config.cluster,
        "hostname": socket.gethostname(),
        "files": [],
    }

    for path in files:
        digest = sha256_file(path)
        key = basebackup_key(config, backup_id, path.name)
        upload_file(client, config, path, key, args.dry_run)
        manifest["files"].append(
            {
                "name": path.name,
                "key": key,
                "size_bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
        print(
            json.dumps(
                {
                    "action": "uploaded_basebackup"
                    if not args.dry_run
                    else "planned_basebackup",
                    "filename": path.name,
                    "key": key,
                    "size_bytes": path.stat().st_size,
                },
                sort_keys=True,
            )
        )

    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    manifest_key = basebackup_key(config, backup_id, "manifest.json")
    if args.dry_run:
        print(json.dumps({"action": "dry_run_manifest", "key": manifest_key}))
    else:
        client.put_object(
            Bucket=config.bucket,
            Key=manifest_key,
            Body=manifest_bytes,
            ContentType="application/json",
            CacheControl="private, max-age=0, no-store",
        )
        client.head_object(Bucket=config.bucket, Key=manifest_key)

    print(
        json.dumps(
            {
                "kind": "basebackup",
                "backup_id": backup_id,
                "files": len(files),
                "manifest_key": manifest_key,
            },
            sort_keys=True,
        )
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload PostgreSQL PITR WAL/basebackup files to private S3/R2."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    wal = subparsers.add_parser("wal", help="Upload archived WAL files")
    wal.add_argument("--archive-dir", default="/postgres-wal-archive")
    wal.add_argument("--dry-run", action="store_true")
    wal.add_argument(
        "--delete-after-upload",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delete local WAL files only after successful upload and head check.",
    )
    wal.set_defaults(func=upload_wal)

    basebackup = subparsers.add_parser("basebackup", help="Upload a pg_basebackup dir")
    basebackup.add_argument("--source-dir", required=True)
    basebackup.add_argument("--backup-id", default="")
    basebackup.add_argument("--dry-run", action="store_true")
    basebackup.set_defaults(func=upload_basebackup)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
