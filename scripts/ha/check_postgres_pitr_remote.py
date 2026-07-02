#!/usr/bin/env python3
"""Check private S3/R2 PostgreSQL PITR objects without printing secrets."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _load_upload_helpers() -> tuple[Any, Any]:
    try:
        from scripts.ha.upload_postgres_pitr_to_s3 import build_client, load_config

        return build_client, load_config
    except ModuleNotFoundError:
        pass

    candidates = [
        os.getenv("POSTGRES_PITR_UPLOAD_HELPER", ""),
        str(Path(__file__).with_name("upload_postgres_pitr_to_s3.py")),
        "/opt/air-api/scripts/ha/upload_postgres_pitr_to_s3.py",
        "/usr/local/sbin/mvn-postgres-pitr-upload",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        helper_path = Path(candidate)
        if not helper_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("mvn_postgres_pitr_upload_helper", helper_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module.build_client, module.load_config

    raise SystemExit(
        "Could not load PostgreSQL PITR upload helper. "
        "Run from the repo root, set POSTGRES_PITR_UPLOAD_HELPER, or install /usr/local/sbin/mvn-postgres-pitr-upload."
    )


build_client, load_config = _load_upload_helpers()


def _latest_object(client: Any, bucket: str, prefix: str, suffix: str = "") -> dict[str, Any] | None:
    paginator = client.get_paginator("list_objects_v2")
    latest: dict[str, Any] | None = None
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = str(item.get("Key") or "")
            if suffix and not key.endswith(suffix):
                continue
            if key.endswith("/"):
                continue
            if latest is None or item.get("LastModified") > latest.get("LastModified"):
                latest = item
    return latest


def _age_hours(last_modified: datetime) -> float:
    if last_modified.tzinfo is None:
        last_modified = last_modified.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - last_modified).total_seconds() / 3600)


def _print_object_status(kind: str, item: dict[str, Any], max_age_hours: float) -> bool:
    last_modified = item["LastModified"]
    age_hours = _age_hours(last_modified)
    status = "fresh" if age_hours <= max_age_hours else "stale"
    print(
        f"pitr_remote_{kind} status={status} "
        f"age_hours={age_hours:.2f} max_age_hours={max_age_hours:g} "
        f"key={item.get('Key')} size_bytes={item.get('Size')}"
    )
    return status == "fresh"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify PostgreSQL PITR basebackup and WAL objects in private S3/R2."
    )
    parser.add_argument("--max-wal-age-minutes", type=float, default=180.0)
    parser.add_argument("--max-basebackup-age-hours", type=float, default=30.0)
    parser.add_argument("--skip-wal", action="store_true")
    parser.add_argument("--skip-basebackup", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    client = build_client(config)

    failures = 0
    base_prefix = f"{config.key_prefix}/{config.cluster}/basebackups/"
    wal_prefix = f"{config.key_prefix}/{config.cluster}/wal/"

    if not args.skip_basebackup:
        latest_basebackup = _latest_object(
            client,
            config.bucket,
            base_prefix,
            suffix="/manifest.json",
        )
        if latest_basebackup is None:
            print(f"pitr_remote_basebackup status=missing prefix={base_prefix}")
            failures += 1
        elif not _print_object_status(
            "basebackup",
            latest_basebackup,
            args.max_basebackup_age_hours,
        ):
            failures += 1

    if not args.skip_wal:
        latest_wal = _latest_object(client, config.bucket, wal_prefix)
        if latest_wal is None:
            print(f"pitr_remote_wal status=missing prefix={wal_prefix}")
            failures += 1
        elif not _print_object_status(
            "wal",
            latest_wal,
            args.max_wal_age_minutes / 60,
        ):
            failures += 1

    print(f"pitr_remote_summary status={'failed' if failures else 'passed'} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
