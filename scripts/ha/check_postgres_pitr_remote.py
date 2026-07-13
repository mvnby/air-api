#!/usr/bin/env python3
"""Check private S3/R2 PostgreSQL PITR objects without printing secrets."""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _load_python_module_from_path(module_name: str, path: Path) -> Any | None:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        loader = importlib.machinery.SourceFileLoader(module_name, str(path))
        spec = importlib.util.spec_from_loader(module_name, loader)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
        module = _load_python_module_from_path("mvn_postgres_pitr_upload_helper", helper_path)
        if module is None:
            continue
        return module.build_client, module.load_config

    raise SystemExit(
        "Could not load PostgreSQL PITR upload helper. "
        "Run from the repo root, set POSTGRES_PITR_UPLOAD_HELPER, or install /usr/local/sbin/mvn-postgres-pitr-upload."
    )


build_client, load_config = _load_upload_helpers()

WAL_SEGMENT_RE = re.compile(r"^[0-9A-F]{24}$")


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


def _object_exists(client: Any, bucket: str, key: str) -> bool:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=key):
        if any(str(item.get("Key") or "") == key for item in page.get("Contents", [])):
            return True
    return False


def _age_hours(last_modified: datetime) -> float:
    if last_modified.tzinfo is None:
        last_modified = last_modified.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - last_modified).total_seconds() / 3600)


def _print_object_status(kind: str, item: dict[str, Any], max_age_hours: float) -> str:
    last_modified = item["LastModified"]
    age_hours = _age_hours(last_modified)
    status = "fresh" if age_hours <= max_age_hours else "stale"
    print(
        f"pitr_remote_{kind} status={status} "
        f"age_hours={age_hours:.2f} max_age_hours={max_age_hours:g} "
        f"key={item.get('Key')} size_bytes={item.get('Size')}"
    )
    return status


def _classify_wal_status(
    age_hours: float,
    max_age_hours: float,
    local_pending_wal_count: int | None,
    expected_wal_present: bool,
) -> str:
    if age_hours <= max_age_hours:
        return "fresh"
    if expected_wal_present and local_pending_wal_count == 0:
        return "idle"
    return "stale"


def _print_wal_status(
    item: dict[str, Any],
    max_age_hours: float,
    local_pending_wal_count: int | None,
    expected_wal_present: bool,
) -> str:
    age_hours = _age_hours(item["LastModified"])
    status = _classify_wal_status(
        age_hours,
        max_age_hours,
        local_pending_wal_count,
        expected_wal_present,
    )
    pending = "unknown" if local_pending_wal_count is None else str(local_pending_wal_count)
    reason = " reason=no_pending_local_wal" if status == "idle" else ""
    print(
        f"pitr_remote_wal status={status} "
        f"age_hours={age_hours:.2f} max_age_hours={max_age_hours:g} "
        f"local_pending_wal_count={pending} "
        f"key={item.get('Key')} size_bytes={item.get('Size')}{reason}"
    )
    return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify PostgreSQL PITR basebackup and WAL objects in private S3/R2."
    )
    parser.add_argument("--max-wal-age-minutes", type=float, default=180.0)
    parser.add_argument("--max-basebackup-age-hours", type=float, default=30.0)
    parser.add_argument("--expected-wal", default="")
    parser.add_argument("--local-pending-wal-count", type=int)
    parser.add_argument("--skip-wal", action="store_true")
    parser.add_argument("--skip-basebackup", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    client = build_client(config)

    failures = 0
    warnings = 0
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
        elif _print_object_status(
            "basebackup",
            latest_basebackup,
            args.max_basebackup_age_hours,
        ) != "fresh":
            failures += 1

    if not args.skip_wal:
        expected_wal = str(args.expected_wal or "").strip().upper()
        expected_wal_present = False
        local_pending_wal_count = args.local_pending_wal_count
        if args.local_pending_wal_count is not None and args.local_pending_wal_count < 0:
            print(
                "pitr_remote_wal status=invalid_pending_count "
                f"local_pending_wal_count={args.local_pending_wal_count}"
            )
            failures += 1
            local_pending_wal_count = None
        if expected_wal and not WAL_SEGMENT_RE.fullmatch(expected_wal):
            print(f"pitr_remote_wal_expected status=invalid wal={expected_wal}")
            failures += 1
        elif expected_wal:
            expected_key = (
                f"{wal_prefix}{expected_wal[:8]}/{expected_wal}"
            )
            expected_wal_present = _object_exists(client, config.bucket, expected_key)
            if expected_wal_present:
                print(
                    "pitr_remote_wal_expected status=present "
                    f"wal={expected_wal} key={expected_key}"
                )
            else:
                print(
                    "pitr_remote_wal_expected status=missing "
                    f"wal={expected_wal} key={expected_key}"
                )
                failures += 1

        latest_wal = _latest_object(client, config.bucket, wal_prefix)
        if latest_wal is None:
            print(f"pitr_remote_wal status=missing prefix={wal_prefix}")
            failures += 1
        else:
            wal_status = _print_wal_status(
                latest_wal,
                args.max_wal_age_minutes / 60,
                local_pending_wal_count,
                expected_wal_present,
            )
            if wal_status == "stale":
                failures += 1
            elif wal_status == "idle":
                warnings += 1

    print(
        f"pitr_remote_summary status={'failed' if failures else 'passed'} "
        f"failures={failures} warnings={warnings}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
