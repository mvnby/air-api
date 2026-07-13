#!/usr/bin/env python3
"""Prepare an isolated PostgreSQL PITR restore from private S3/R2 artifacts.

This helper never touches the production data directory. It downloads a chosen
physical basebackup into an operator-supplied empty target directory, extracts it
under `data/`, and writes recovery settings that fetch archived WAL from the
private PITR bucket.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

WAL_NAME_RE = re.compile(
    r"^(?:[0-9A-F]{24}|[0-9A-F]{24}\.[0-9A-F]{8}\.backup|[0-9A-F]{8}\.history)$"
)
DEFAULT_WAL_SEGMENT_SIZE_BYTES = 16 * 1024 * 1024
DEFAULT_MIN_FREE_BYTES = 1024 * 1024 * 1024


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


def _load_upload_helpers() -> tuple[Any, Any, Any]:
    try:
        from scripts.ha.upload_postgres_pitr_to_s3 import (
            build_client,
            load_config,
            sha256_file,
        )

        return build_client, load_config, sha256_file
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
        module_name = "mvn_postgres_pitr_upload_helper"
        module = _load_python_module_from_path(module_name, helper_path)
        if module is None:
            continue
        return module.build_client, module.load_config, module.sha256_file

    raise SystemExit(
        "Could not load PostgreSQL PITR upload helper. "
        "Run from the repo root, set POSTGRES_PITR_UPLOAD_HELPER, or install /usr/local/sbin/mvn-postgres-pitr-upload."
    )


build_client, load_config, sha256_file = _load_upload_helpers()


@dataclass(frozen=True)
class BasebackupManifest:
    backup_id: str
    created_at: datetime
    key: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class WalObject:
    key: str
    filename: str
    size_bytes: int


def _read_s3_body(body: Any) -> bytes:
    data = body.read()
    if isinstance(data, str):
        return data.encode("utf-8")
    return bytes(data)


def _parse_datetime(value: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("empty datetime")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _manifest_prefix(config: Any) -> str:
    return f"{config.key_prefix}/{config.cluster}/basebackups/"


def _wal_key(config: Any, wal_name: str) -> str:
    timeline = wal_name[:8]
    return f"{config.key_prefix}/{config.cluster}/wal/{timeline}/{wal_name}"


def _list_manifest_keys(client: Any, bucket: str, prefix: str) -> list[str]:
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = str(item.get("Key") or "")
            if key.endswith("/manifest.json"):
                keys.append(key)
    return sorted(keys)


def _list_wal_objects(client: Any, config: Any) -> list[WalObject]:
    prefix = f"{config.key_prefix}/{config.cluster}/wal/"
    paginator = client.get_paginator("list_objects_v2")
    objects: list[WalObject] = []
    for page in paginator.paginate(Bucket=config.bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = str(item.get("Key") or "")
            filename = key.rsplit("/", 1)[-1]
            if key.endswith("/") or not WAL_NAME_RE.match(filename):
                continue
            objects.append(
                WalObject(
                    key=key,
                    filename=filename,
                    size_bytes=int(item.get("Size") or 0),
                )
            )
    return sorted(objects, key=lambda item: item.filename)


def _parse_lsn(value: str) -> int:
    try:
        high, low = value.split("/", 1)
        return (int(high, 16) << 32) + int(low, 16)
    except (AttributeError, TypeError, ValueError) as exc:
        raise SystemExit(f"Invalid WAL LSN in backup_manifest: {value!r}") from exc


def _wal_segment_name(*, timeline: int, lsn: str, segment_size_bytes: int) -> str:
    if (
        segment_size_bytes <= 0
        or segment_size_bytes > 0x100000000
        or 0x100000000 % segment_size_bytes != 0
    ):
        raise SystemExit(
            "WAL segment size must be a positive divisor of 2^32 bytes; "
            f"got {segment_size_bytes}"
        )
    if timeline <= 0:
        raise SystemExit(f"Invalid WAL timeline in backup_manifest: {timeline}")

    segments_per_log = 0x100000000 // segment_size_bytes
    segment_number = _parse_lsn(lsn) // segment_size_bytes
    log = segment_number // segments_per_log
    segment = segment_number % segments_per_log
    return f"{timeline:08X}{log:08X}{segment:08X}"


def _backup_manifest_entry(manifest: BasebackupManifest) -> dict[str, Any]:
    for item in manifest.payload.get("files") or []:
        if isinstance(item, dict) and item.get("name") == "backup_manifest":
            if item.get("key"):
                return item
            break
    raise SystemExit(
        f"Basebackup {manifest.backup_id} has no backup_manifest file; "
        "cannot select a safe WAL range"
    )


def _load_postgres_backup_manifest(
    client: Any, bucket: str, manifest: BasebackupManifest
) -> dict[str, Any]:
    entry = _backup_manifest_entry(manifest)
    response = client.get_object(Bucket=bucket, Key=str(entry["key"]))
    try:
        payload = json.loads(_read_s3_body(response["Body"]).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Invalid PostgreSQL backup_manifest for {manifest.backup_id}"
        ) from exc
    if not isinstance(payload, dict):
        raise SystemExit(
            f"Invalid PostgreSQL backup_manifest for {manifest.backup_id}"
        )
    return payload


def _backup_start_wal_name(
    postgres_manifest: dict[str, Any], *, segment_size_bytes: int
) -> str:
    raw_ranges = postgres_manifest.get("WAL-Ranges")
    if not isinstance(raw_ranges, list) or not raw_ranges:
        raise SystemExit("PostgreSQL backup_manifest has no WAL-Ranges")

    starts: list[tuple[int, int, str]] = []
    for item in raw_ranges:
        if not isinstance(item, dict):
            raise SystemExit("PostgreSQL backup_manifest has an invalid WAL-Ranges entry")
        try:
            timeline = int(item.get("Timeline"))
        except (TypeError, ValueError) as exc:
            raise SystemExit(
                f"Invalid WAL timeline in backup_manifest: {item.get('Timeline')!r}"
            ) from exc
        start_lsn = str(item.get("Start-LSN") or "")
        starts.append((timeline, _parse_lsn(start_lsn), start_lsn))

    timeline, _numeric_lsn, start_lsn = min(starts)
    return _wal_segment_name(
        timeline=timeline,
        lsn=start_lsn,
        segment_size_bytes=segment_size_bytes,
    )


def _wal_position(filename: str) -> tuple[int, int, int] | None:
    if filename.endswith(".history"):
        return None
    base = filename[:24]
    if len(base) != 24:
        return None
    try:
        return int(base[:8], 16), int(base[8:16], 16), int(base[16:24], 16)
    except ValueError:
        return None


def _select_wal_objects(
    objects: list[WalObject], *, start_wal_name: str
) -> list[WalObject]:
    start_position = _wal_position(start_wal_name)
    if start_position is None:
        raise SystemExit(f"Invalid start WAL filename: {start_wal_name}")
    start_timeline = start_position[0]

    selected: list[WalObject] = []
    for item in objects:
        if item.filename.endswith(".history"):
            try:
                history_timeline = int(item.filename[:8], 16)
            except ValueError:
                continue
            if history_timeline >= start_timeline:
                selected.append(item)
            continue

        position = _wal_position(item.filename)
        if position is not None and position >= start_position:
            selected.append(item)
    return selected


def _estimated_extracted_bytes(postgres_manifest: dict[str, Any]) -> int:
    files = postgres_manifest.get("Files")
    if not isinstance(files, list):
        return 0
    total = 0
    for item in files:
        if not isinstance(item, dict):
            continue
        try:
            total += max(0, int(item.get("Size") or 0))
        except (TypeError, ValueError):
            continue
    return total


def _basebackup_download_bytes(files: list[Any]) -> int:
    total = 0
    for item in files:
        if not isinstance(item, dict):
            raise SystemExit(f"Basebackup manifest file entry is invalid: {item!r}")
        try:
            size_bytes = int(item.get("size_bytes"))
        except (TypeError, ValueError) as exc:
            raise SystemExit(
                f"Basebackup manifest has invalid size_bytes: {item!r}"
            ) from exc
        if size_bytes < 0:
            raise SystemExit(f"Basebackup manifest has negative size_bytes: {item!r}")
        total += size_bytes
    return total


def _ensure_restore_space(
    target_dir: Path,
    *,
    basebackup_bytes: int,
    extracted_bytes: int,
    wal_bytes: int,
    min_free_bytes: int,
) -> tuple[int, int]:
    if min_free_bytes < 0:
        raise SystemExit("PITR restore minimum free bytes must not be negative")
    available_bytes = shutil.disk_usage(target_dir).free
    restore_bytes = basebackup_bytes + extracted_bytes + wal_bytes
    required_bytes = restore_bytes + min_free_bytes
    if available_bytes < required_bytes:
        raise SystemExit(
            "Insufficient free space for PITR prepare: "
            f"available_bytes={available_bytes} required_bytes={required_bytes} "
            f"basebackup_bytes={basebackup_bytes} extracted_bytes={extracted_bytes} "
            f"wal_bytes={wal_bytes} reserve_bytes={min_free_bytes}"
        )
    return available_bytes, required_bytes


def _load_manifest(client: Any, bucket: str, key: str) -> BasebackupManifest:
    response = client.get_object(Bucket=bucket, Key=key)
    payload = json.loads(_read_s3_body(response["Body"]).decode("utf-8"))
    backup_id = str(payload.get("backup_id") or key.rstrip("/").split("/")[-2])
    created_at = _parse_datetime(str(payload.get("created_at") or backup_id))
    return BasebackupManifest(
        backup_id=backup_id,
        created_at=created_at,
        key=key,
        payload=payload,
    )


def list_manifests(client: Any, config: Any) -> list[BasebackupManifest]:
    keys = _list_manifest_keys(client, config.bucket, _manifest_prefix(config))
    manifests = [_load_manifest(client, config.bucket, key) for key in keys]
    return sorted(manifests, key=lambda item: item.created_at)


def select_manifest(
    manifests: list[BasebackupManifest],
    *,
    backup_id: str = "",
    target_time: datetime | None = None,
) -> BasebackupManifest:
    if backup_id:
        for manifest in manifests:
            if manifest.backup_id == backup_id:
                return manifest
        raise SystemExit(f"Basebackup not found: {backup_id}")

    if not manifests:
        raise SystemExit("No PITR basebackup manifests found")

    if target_time is None:
        return manifests[-1]

    eligible = [manifest for manifest in manifests if manifest.created_at <= target_time]
    if not eligible:
        raise SystemExit(
            "No basebackup exists before target time "
            f"{target_time.isoformat()}"
        )
    return eligible[-1]


def _ensure_empty_target_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise SystemExit(f"Target directory must be empty: {path}")


def _download_file(client: Any, bucket: str, key: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_name(f".{destination.name}.tmp")
    client.download_file(bucket, key, str(tmp_path))
    tmp_path.replace(destination)


def _verify_download(path: Path, expected_sha256: str) -> None:
    actual = sha256_file(path)
    if actual != expected_sha256:
        path.unlink(missing_ok=True)
        raise SystemExit(
            f"Checksum mismatch for {path.name}: expected {expected_sha256}, got {actual}"
        )


def _safe_extract_tar_gz(tar_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tar:
        root = destination.resolve()
        for member in tar.getmembers():
            member_path = (destination / member.name).resolve()
            if member_path != root and root not in member_path.parents:
                raise SystemExit(f"Unsafe tar member path in {tar_path.name}: {member.name}")
        tar.extractall(destination)


def _postgres_conf_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _write_recovery_settings(
    *,
    data_dir: Path,
    target_time: datetime | None,
    wal_mode: str,
    restore_mount_path: str,
    restore_helper_path: str,
) -> None:
    if wal_mode == "local":
        restore_command = f"cp {shlex.quote(restore_mount_path.rstrip('/') + '/wal/%f')} %p"
    elif wal_mode == "remote":
        restore_command = (
            f"python3 {shlex.quote(restore_helper_path)} "
            "fetch-wal --wal-name %f --destination %p"
        )
    else:
        raise ValueError(f"Unsupported wal_mode={wal_mode!r}")
    lines = [
        "",
        "# MVN PITR restore settings",
        f"restore_command = {_postgres_conf_quote(restore_command)}",
        "recovery_target_action = 'pause'",
    ]
    if target_time is not None:
        lines.append(f"recovery_target_time = {_postgres_conf_quote(target_time.isoformat())}")

    auto_conf = data_dir / "postgresql.auto.conf"
    with auto_conf.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    (data_dir / "recovery.signal").touch()


def command_list(args: argparse.Namespace) -> int:
    config = load_config()
    client = build_client(config)
    manifests = list_manifests(client, config)
    for manifest in manifests:
        print(
            json.dumps(
                {
                    "backup_id": manifest.backup_id,
                    "created_at": manifest.created_at.isoformat(),
                    "manifest_key": manifest.key,
                    "files": len(manifest.payload.get("files") or []),
                },
                sort_keys=True,
            )
        )
    print(json.dumps({"kind": "basebackup_manifest", "count": len(manifests)}, sort_keys=True))
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    target_dir = Path(args.target_dir).resolve()
    _ensure_empty_target_dir(target_dir)

    target_time = _parse_datetime(args.target_time) if args.target_time else None
    config = load_config()
    client = build_client(config)
    manifest = select_manifest(
        list_manifests(client, config),
        backup_id=args.backup_id,
        target_time=target_time,
    )

    files = manifest.payload.get("files") or []
    if not isinstance(files, list) or not files:
        raise SystemExit(f"Basebackup manifest has no files: {manifest.key}")

    postgres_manifest = _load_postgres_backup_manifest(client, config.bucket, manifest)
    start_wal_name = _backup_start_wal_name(
        postgres_manifest,
        segment_size_bytes=args.wal_segment_size_bytes,
    )
    wal_objects: list[WalObject] = []
    if args.wal_mode == "local":
        wal_objects = _select_wal_objects(
            _list_wal_objects(client, config),
            start_wal_name=start_wal_name,
        )

    basebackup_bytes = _basebackup_download_bytes(files)
    extracted_bytes = _estimated_extracted_bytes(postgres_manifest)
    wal_bytes = sum(item.size_bytes for item in wal_objects)
    available_bytes, required_bytes = _ensure_restore_space(
        target_dir,
        basebackup_bytes=basebackup_bytes,
        extracted_bytes=extracted_bytes,
        wal_bytes=wal_bytes,
        min_free_bytes=args.min_free_bytes,
    )
    print(
        json.dumps(
            {
                "status": "preflight",
                "backup_id": manifest.backup_id,
                "start_wal": start_wal_name,
                "selected_wal": len(wal_objects),
                "selected_wal_bytes": wal_bytes,
                "available_bytes": available_bytes,
                "required_bytes": required_bytes,
            },
            sort_keys=True,
        )
    )

    downloads_dir = target_dir / "downloads"
    data_dir = target_dir / "data"
    downloads_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)

    downloaded: list[Path] = []
    for item in files:
        name = str(item.get("name") or "")
        key = str(item.get("key") or "")
        expected_sha256 = str(item.get("sha256") or "")
        if not name or not key or not expected_sha256:
            raise SystemExit(f"Basebackup manifest file entry is incomplete: {item!r}")
        destination = downloads_dir / name
        _download_file(client, config.bucket, key, destination)
        _verify_download(destination, expected_sha256)
        downloaded.append(destination)

    base_tar = downloads_dir / "base.tar.gz"
    if not base_tar.is_file():
        raise SystemExit("Downloaded basebackup is missing base.tar.gz")
    _safe_extract_tar_gz(base_tar, data_dir)

    wal_tar = downloads_dir / "pg_wal.tar.gz"
    if wal_tar.is_file():
        _safe_extract_tar_gz(wal_tar, data_dir / "pg_wal")

    downloaded_wal = 0
    if args.wal_mode == "local":
        wal_dir = target_dir / "wal"
        wal_dir.mkdir(parents=True)
        for item in wal_objects:
            _download_file(client, config.bucket, item.key, wal_dir / item.filename)
            downloaded_wal += 1

    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.payload, indent=2, sort_keys=True) + "\n")
    _write_recovery_settings(
        data_dir=data_dir,
        target_time=target_time,
        wal_mode=args.wal_mode,
        restore_mount_path=args.restore_mount_path,
        restore_helper_path=args.restore_helper_path,
    )

    print(
        json.dumps(
            {
                "status": "prepared",
                "backup_id": manifest.backup_id,
                "created_at": manifest.created_at.isoformat(),
                "target_dir": str(target_dir),
                "data_dir": str(data_dir),
                "downloaded_files": len(downloaded),
                "downloaded_wal": downloaded_wal,
                "downloaded_wal_bytes": wal_bytes,
                "start_wal": start_wal_name,
                "wal_mode": args.wal_mode,
            },
            sort_keys=True,
        )
    )
    return 0


def command_fetch_wal(args: argparse.Namespace) -> int:
    wal_name = str(args.wal_name or "").strip()
    if not WAL_NAME_RE.match(wal_name):
        raise SystemExit(f"Invalid WAL filename: {wal_name}")

    destination = Path(args.destination)
    config = load_config()
    client = build_client(config)
    key = _wal_key(config, wal_name)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=str(destination.parent), delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        client.download_file(config.bucket, key, str(tmp_path))
        if tmp_path.stat().st_size <= 0:
            raise SystemExit(f"Downloaded WAL file is empty: {wal_name}")
        tmp_path.replace(destination)
    finally:
        tmp_path.unlink(missing_ok=True)

    print(json.dumps({"status": "fetched", "wal_name": wal_name, "key": key}, sort_keys=True))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare an isolated PostgreSQL PITR restore from private S3/R2."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_cmd = subparsers.add_parser("list-basebackups", help="List remote basebackup manifests")
    list_cmd.set_defaults(func=command_list)

    prepare = subparsers.add_parser(
        "prepare",
        help="Download and extract a basebackup into an empty restore directory",
    )
    prepare.add_argument("--target-dir", required=True)
    prepare.add_argument("--backup-id", default="")
    prepare.add_argument(
        "--target-time",
        default="",
        help="UTC restore target timestamp. The newest basebackup at or before this time is selected.",
    )
    prepare.add_argument(
        "--wal-mode",
        choices=("local", "remote"),
        default="local",
        help=(
            "local downloads archived WAL into target-dir/wal and writes a cp restore_command; "
            "remote writes a Python/R2 restore_command for containers that include this helper and boto3."
        ),
    )
    prepare.add_argument(
        "--wal-segment-size-bytes",
        type=int,
        default=int(
            os.getenv(
                "POSTGRES_WAL_SEGMENT_SIZE_BYTES",
                str(DEFAULT_WAL_SEGMENT_SIZE_BYTES),
            )
        ),
        help="WAL segment size used to convert backup Start-LSN into a WAL filename.",
    )
    prepare.add_argument(
        "--min-free-bytes",
        type=int,
        default=int(
            os.getenv("PITR_RESTORE_MIN_FREE_BYTES", str(DEFAULT_MIN_FREE_BYTES))
        ),
        help="Free disk space that must remain after estimated download and extraction.",
    )
    prepare.add_argument(
        "--restore-mount-path",
        default="/pitr-restore",
        help="Path where target-dir will be mounted inside the restore PostgreSQL container in local WAL mode.",
    )
    prepare.add_argument(
        "--restore-helper-path",
        default="/app/scripts/ha/restore_postgres_pitr_from_s3.py",
        help="Path visible inside the restore PostgreSQL container for restore_command.",
    )
    prepare.set_defaults(func=command_prepare)

    fetch_wal = subparsers.add_parser("fetch-wal", help="Fetch one WAL file for restore_command")
    fetch_wal.add_argument("--wal-name", required=True)
    fetch_wal.add_argument("--destination", required=True)
    fetch_wal.set_defaults(func=command_fetch_wal)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
