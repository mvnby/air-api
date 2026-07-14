#!/usr/bin/env python3
"""Prepare an isolated PostgreSQL PITR restore from private S3/R2 artifacts.

The restore path treats every remote object as untrusted.  A restore is prepared
only from the exact outer manifest schema, the expected PostgreSQL system
identifier, a matching PostgreSQL ``backup_manifest`` lineage, and one complete
timeline-history-proven WAL chain ending at an operator-supplied WAL segment.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DEFAULT_WAL_SEGMENT_SIZE_BYTES = 16 * 1024 * 1024
DEFAULT_MIN_FREE_BYTES = 1024 * 1024 * 1024
MAX_BASEBACKUP_MANIFEST_BYTES = 1024 * 1024
MAX_LISTED_MANIFESTS = 4096
MAX_LISTED_WAL_OBJECTS = 262144
MAX_RESTORE_TAR_MEMBERS = 250000


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
    explicit = os.getenv("POSTGRES_PITR_UPLOAD_HELPER", "").strip()
    if explicit:
        helper_path = Path(explicit)
        if not helper_path.is_absolute() or not helper_path.is_file():
            raise SystemExit("Explicit PostgreSQL PITR upload helper is invalid")
        module = _load_python_module_from_path(
            "mvn_postgres_pitr_upload_helper",
            helper_path,
        )
        if module is None:
            raise SystemExit("Explicit PostgreSQL PITR upload helper could not be loaded")
        return module.build_client, module.load_config

    try:
        from scripts.ha.upload_postgres_pitr_to_s3 import build_client, load_config

        return build_client, load_config
    except ModuleNotFoundError:
        pass

    raise SystemExit(
        "Could not load PostgreSQL PITR upload helper. "
        "Run from the repo root or set POSTGRES_PITR_UPLOAD_HELPER."
    )


def _load_support_module(
    *, env_name: str, module_name: str, repository_name: str, label: str
) -> Any:
    explicit = os.getenv(env_name, "").strip()
    if explicit:
        helper_path = Path(explicit)
        if not helper_path.is_absolute() or not helper_path.is_file():
            raise SystemExit(f"Explicit PITR {label} helper is invalid")
        module = _load_python_module_from_path(module_name, helper_path)
        if module is None:
            raise SystemExit(f"Explicit PITR {label} helper could not be loaded")
        return module
    try:
        return importlib.import_module(f"scripts.ha.{repository_name}")
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"Could not load PITR {label} helper. Run from the repo root or set "
            f"{env_name}."
        ) from exc


build_client, load_config = _load_upload_helpers()
artifact_security = _load_support_module(
    env_name="POSTGRES_PITR_ARTIFACT_SECURITY_HELPER",
    module_name="mvn_postgres_pitr_artifact_security",
    repository_name="postgres_pitr_artifact_security",
    label="artifact security",
)
wal_lineage = _load_support_module(
    env_name="POSTGRES_PITR_WAL_LINEAGE_HELPER",
    module_name="mvn_postgres_pitr_wal_lineage",
    repository_name="postgres_pitr_wal_lineage",
    label="WAL lineage",
)
recovery_config = _load_support_module(
    env_name="POSTGRES_PITR_RECOVERY_CONFIG_HELPER",
    module_name="mvn_postgres_pitr_recovery_config",
    repository_name="postgres_pitr_recovery_config",
    label="recovery config",
)
BasebackupManifest = artifact_security.BasebackupManifest
WalObject = wal_lineage.WalObject
WalSelection = wal_lineage.WalSelection
WAL_NAME_RE = wal_lineage.WAL_NAME_RE
WAL_SEGMENT_RE = wal_lineage.WAL_SEGMENT_RE
RESTORE_POINT_RE = artifact_security.RESTORE_POINT_RE
SHA256_RE = artifact_security.SHA256_RE
OUTER_MANIFEST_KEYS = artifact_security.OUTER_MANIFEST_KEYS
OUTER_FILE_KEYS = artifact_security.OUTER_FILE_KEYS
_parse_canonical_utc = artifact_security.parse_canonical_utc
_parse_canonical_lsn = artifact_security.parse_canonical_lsn
_validate_system_identifier = artifact_security.validate_system_identifier
_validate_postgres_manifest_lineage = (
    artifact_security.validate_postgres_manifest_lineage
)
_wal_segment_name = wal_lineage.wal_segment_name
_wal_segment_position = wal_lineage.wal_segment_position
_select_wal_objects = wal_lineage.select_wal_objects


def _manifest_prefix(config: Any) -> str:
    return f"{config.key_prefix}/{config.cluster}/basebackups/"


def _wal_prefix(config: Any) -> str:
    return f"{config.key_prefix}/{config.cluster}/wal/"


def _wal_key(config: Any, wal_name: str) -> str:
    return f"{_wal_prefix(config)}{wal_name[:8]}/{wal_name}"


def _list_manifest_keys(client: Any, bucket: str, prefix: str) -> list[str]:
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    seen_keys: set[str] = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = str(item.get("Key") or "")
            if key.endswith("/manifest.json"):
                if key in seen_keys:
                    raise SystemExit(f"Duplicate PITR basebackup manifest key: {key}")
                seen_keys.add(key)
                keys.append(key)
                if len(keys) > MAX_LISTED_MANIFESTS:
                    raise SystemExit("Too many PITR basebackup manifests")
    return sorted(keys)


def _list_wal_objects(client: Any, config: Any) -> list[WalObject]:
    return wal_lineage.list_wal_objects(
        client,
        bucket=config.bucket,
        prefix=_wal_prefix(config),
        max_objects=MAX_LISTED_WAL_OBJECTS,
    )


def _read_verified_history(client: Any, config: Any, item: WalObject) -> bytes:
    digest = artifact_security.object_sha256(
        client,
        bucket=config.bucket,
        key=item.key,
        expected_size=item.size_bytes,
    )
    return artifact_security.read_verified_object(
        client,
        bucket=config.bucket,
        key=item.key,
        expected_size=item.size_bytes,
        expected_sha256=digest,
        maximum_size=wal_lineage.MAX_TIMELINE_HISTORY_BYTES,
        label=f"PostgreSQL timeline history {item.filename}",
    )


def _validate_outer_manifest(
    *,
    payload: dict[str, Any],
    manifest_key: str,
    config: Any,
    expected_system_identifier: str | None,
) -> BasebackupManifest:
    return artifact_security.validate_outer_manifest(
        payload=payload,
        manifest_key=manifest_key,
        key_prefix=config.key_prefix,
        cluster=config.cluster,
        expected_system_identifier=expected_system_identifier,
    )


def _load_manifest(
    client: Any,
    config: Any,
    key: str,
    *,
    expected_system_identifier: str | None,
) -> BasebackupManifest | None:
    head = client.head_object(Bucket=config.bucket, Key=key)
    try:
        expected_size = int(head["ContentLength"])
        metadata = head.get("Metadata") or {}
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"Basebackup manifest metadata is incomplete: {key}") from exc
    if not isinstance(metadata, dict) or expected_size <= 0:
        raise SystemExit(f"Basebackup manifest metadata is incomplete: {key}")
    digest_value = metadata.get("sha256")
    expected_sha256 = digest_value if isinstance(digest_value, str) else ""
    if digest_value is not None and digest_value != "" and not SHA256_RE.fullmatch(expected_sha256):
        raise SystemExit(f"Basebackup manifest digest metadata is invalid: {key}")
    reader = (
        artifact_security.read_verified_object
        if expected_sha256
        else artifact_security.read_bounded_object_without_digest
    )
    reader_args = dict(
        bucket=config.bucket,
        key=key,
        expected_size=expected_size,
        maximum_size=MAX_BASEBACKUP_MANIFEST_BYTES,
        label="Basebackup manifest",
    )
    if expected_sha256:
        reader_args["expected_sha256"] = expected_sha256
    raw_payload = reader(client, **reader_args)
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Basebackup manifest is invalid JSON: {key}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Basebackup manifest is not a JSON object: {key}")
    # Manifests written before the lineage-bound v1 contract had no explicit
    # schema version and cannot be restored safely.  They are still common in
    # an upgraded bucket, so consume them only through the same bounded,
    # digest-verified read above and omit them from selection.  Anything that
    # claims a schema version is authoritative input: unsupported or malformed
    # claimed-v1 payloads must fail the whole inventory instead of being
    # silently downgraded to legacy data.
    if "schema_version" not in payload:
        artifact_security.validate_legacy_v0_manifest(
            payload=payload,
            manifest_key=key,
            key_prefix=config.key_prefix,
            cluster=config.cluster,
        )
        return None
    if not expected_sha256:
        raise SystemExit(f"Versioned basebackup manifest has no digest metadata: {key}")
    return _validate_outer_manifest(
        payload=payload,
        manifest_key=key,
        config=config,
        expected_system_identifier=expected_system_identifier,
    )


def list_manifests(
    client: Any,
    config: Any,
    *,
    expected_system_identifier: str | None = None,
) -> list[BasebackupManifest]:
    keys = _list_manifest_keys(client, config.bucket, _manifest_prefix(config))
    loaded = [
        _load_manifest(
            client,
            config,
            key,
            expected_system_identifier=expected_system_identifier,
        )
        for key in keys
    ]
    manifests = [manifest for manifest in loaded if manifest is not None]
    return sorted(manifests, key=lambda item: item.completed_at)


def select_manifest(
    manifests: list[BasebackupManifest],
    *,
    backup_id: str = "",
    target_time: datetime | None,
) -> BasebackupManifest:
    eligible = manifests if target_time is None else [
        manifest for manifest in manifests if manifest.completed_at <= target_time
    ]
    if backup_id:
        for manifest in eligible:
            if manifest.backup_id == backup_id:
                return manifest
        raise SystemExit(f"Eligible basebackup not found: {backup_id}")
    if not eligible:
        suffix = f" before target time {target_time.isoformat()}" if target_time else ""
        raise SystemExit(f"No eligible basebackup{suffix}")
    return eligible[-1]


def _backup_manifest_entry(manifest: BasebackupManifest) -> Any:
    for item in manifest.files:
        if item.name == "backup_manifest":
            return item
    raise SystemExit(
        f"Basebackup {manifest.backup_id} has no backup_manifest file; "
        "cannot prove its WAL lineage"
    )


def _load_postgres_backup_manifest(
    client: Any,
    config: Any,
    manifest: BasebackupManifest,
) -> dict[str, Any]:
    entry = _backup_manifest_entry(manifest)
    raw_payload = artifact_security.read_verified_object(
        client,
        bucket=config.bucket,
        key=entry.key,
        expected_size=entry.size_bytes,
        expected_sha256=entry.sha256,
        maximum_size=artifact_security.MAX_POSTGRES_MANIFEST_BYTES,
        label="PostgreSQL backup_manifest",
    )
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Invalid PostgreSQL backup_manifest for {manifest.backup_id}"
        ) from exc
    if not isinstance(payload, dict):
        raise SystemExit(
            f"Invalid PostgreSQL backup_manifest for {manifest.backup_id}"
        )
    return payload


def command_list(args: argparse.Namespace) -> int:
    config = load_config()
    client = build_client(config)
    manifests = list_manifests(client, config)
    for manifest in manifests:
        print(
            json.dumps(
                {
                    "backup_id": manifest.backup_id,
                    "completed_at": manifest.completed_at.isoformat(),
                    "manifest_key": manifest.key,
                    "system_identifier": manifest.system_identifier,
                    "timeline": manifest.timeline,
                    "files": len(manifest.files),
                },
                sort_keys=True,
            )
        )
    print(json.dumps({"kind": "basebackup_manifest", "count": len(manifests)}, sort_keys=True))
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    expected_system_identifier = _validate_system_identifier(
        args.expected_system_identifier,
        label="Expected PostgreSQL system identifier",
    )
    if not WAL_SEGMENT_RE.fullmatch(args.required_end_wal):
        raise SystemExit("Required end WAL is invalid")
    if bool(args.target_time) == bool(args.target_name) or bool(args.target_name) != bool(args.target_lsn):
        raise SystemExit("Specify either target time or target name with its exact LSN")
    target_time = (
        _parse_canonical_utc(args.target_time, label="Restore target time")
        if args.target_time
        else None
    )
    if target_time and target_time >= datetime.now(timezone.utc):
        raise SystemExit("Restore target time must be in the past")
    if args.target_name and not RESTORE_POINT_RE.fullmatch(args.target_name):
        raise SystemExit("Restore target name is invalid")
    target_lsn_value = (
        _parse_canonical_lsn(args.target_lsn, label="Restore target LSN")
        if args.target_lsn
        else None
    )

    target_dir = Path(args.target_dir).resolve()
    artifact_security.ensure_empty_target_dir(target_dir)
    config = load_config()
    client = build_client(config)
    manifest = select_manifest(
        list_manifests(
            client,
            config,
            expected_system_identifier=expected_system_identifier,
        ),
        backup_id=args.backup_id,
        target_time=target_time,
    )
    postgres_manifest = _load_postgres_backup_manifest(client, config, manifest)
    postgres_start_lsn, postgres_end_lsn = _validate_postgres_manifest_lineage(
        manifest,
        postgres_manifest,
    )
    start_wal_name = _wal_segment_name(
        timeline=manifest.timeline,
        lsn=postgres_start_lsn,
        segment_size_bytes=args.wal_segment_size_bytes,
    )
    minimum_end_value = max(
        _parse_canonical_lsn(postgres_end_lsn, label="PostgreSQL backup end LSN"),
        _parse_canonical_lsn(manifest.end_lsn, label="Basebackup end LSN"),
    )
    if target_lsn_value is not None:
        if target_lsn_value < minimum_end_value:
            raise SystemExit("Restore target LSN precedes the completed basebackup")
        minimum_end_value = target_lsn_value
    minimum_end_wal = _wal_segment_name(
        timeline=manifest.timeline,
        lsn=f"{minimum_end_value >> 32:X}/{minimum_end_value & 0xFFFFFFFF:X}",
        segment_size_bytes=args.wal_segment_size_bytes,
    )
    _, minimum_end_position = _wal_segment_position(
        minimum_end_wal,
        segment_size_bytes=args.wal_segment_size_bytes,
    )
    _, required_end_position = _wal_segment_position(
        args.required_end_wal,
        segment_size_bytes=args.wal_segment_size_bytes,
    )
    if required_end_position < minimum_end_position:
        raise SystemExit("Required end WAL does not cover the completed basebackup")

    selection = _select_wal_objects(
        _list_wal_objects(client, config),
        start_wal_name=start_wal_name,
        start_lsn=postgres_start_lsn,
        required_end_wal=args.required_end_wal,
        segment_size_bytes=args.wal_segment_size_bytes,
        history_loader=lambda item: _read_verified_history(client, config, item),
    )
    wal_objects = selection.objects if args.wal_mode == "local" else ()
    basebackup_bytes = sum(item.size_bytes for item in manifest.files)
    extracted_bytes = artifact_security.estimated_extracted_bytes(postgres_manifest)
    wal_bytes = sum(item.size_bytes for item in wal_objects)
    available_bytes, required_bytes = artifact_security.ensure_restore_space(
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
                "system_identifier": manifest.system_identifier,
                "timeline": manifest.timeline,
                "start_wal": start_wal_name,
                "required_end_wal": args.required_end_wal,
                "selected_segments": len(selection.segments),
                "selected_history": len(selection.history_files),
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
    for item in manifest.files:
        artifact_security.download_verified_object(
            client,
            bucket=config.bucket,
            key=item.key,
            destination=downloads_dir / item.name,
            expected_size=item.size_bytes,
            expected_sha256=item.sha256,
        )

    postgres_files = postgres_manifest.get("Files")
    postgres_file_count = len(postgres_files) if isinstance(postgres_files, list) else 0
    if postgres_file_count > MAX_RESTORE_TAR_MEMBERS - 1024:
        raise SystemExit("PostgreSQL backup manifest has too many files")
    max_tar_members = max(1024, postgres_file_count + 1024)
    extraction_budget = max(0, available_bytes - args.min_free_bytes - wal_bytes)
    artifact_security.safe_extract_tar_gz(
        downloads_dir / "base.tar.gz",
        data_dir,
        max_members=max_tar_members,
        max_expanded_bytes=extraction_budget,
    )
    wal_tar = downloads_dir / "pg_wal.tar.gz"
    if wal_tar.is_file():
        remaining_budget = max(
            0,
            shutil.disk_usage(target_dir).free - args.min_free_bytes - wal_bytes,
        )
        artifact_security.safe_extract_tar_gz(
            wal_tar,
            data_dir / "pg_wal",
            max_members=max_tar_members,
            max_expanded_bytes=remaining_budget,
        )

    downloaded_wal = 0
    if args.wal_mode == "local":
        wal_dir = target_dir / "wal"
        wal_dir.mkdir(parents=True)
        for item in wal_objects:
            expected_sha256 = artifact_security.object_sha256(
                client,
                bucket=config.bucket,
                key=item.key,
                expected_size=item.size_bytes,
            )
            artifact_security.download_verified_object(
                client,
                bucket=config.bucket,
                key=item.key,
                destination=wal_dir / item.filename,
                expected_size=item.size_bytes,
                expected_sha256=expected_sha256,
            )
            downloaded_wal += 1

    (target_dir / "manifest.json").write_text(
        json.dumps(manifest.payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (target_dir / "restore-contract.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "backup_id": manifest.backup_id,
                "expected_system_identifier": expected_system_identifier,
                "timeline": manifest.timeline,
                "target_mode": "time" if target_time else "name",
                "target_time": args.target_time,
                "target_name": args.target_name,
                "target_lsn": args.target_lsn,
                "start_wal": start_wal_name,
                "required_end_wal": args.required_end_wal,
                "selected_segments": len(selection.segments),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    recovery_config.write_recovery_settings(
        data_dir=data_dir,
        control_dir=target_dir / "control",
        target_time=target_time,
        target_name=args.target_name,
        wal_mode=args.wal_mode,
        restore_mount_path=args.restore_mount_path,
        restore_helper_path=args.restore_helper_path,
    )
    print(
        json.dumps(
            {
                "status": "prepared",
                "backup_id": manifest.backup_id,
                "target_dir": str(target_dir),
                "data_dir": str(data_dir),
                "downloaded_files": len(manifest.files),
                "downloaded_wal": downloaded_wal,
                "downloaded_wal_bytes": wal_bytes,
                "start_wal": start_wal_name,
                "required_end_wal": args.required_end_wal,
                "wal_mode": args.wal_mode,
            },
            sort_keys=True,
        )
    )
    return 0


def command_fetch_wal(args: argparse.Namespace) -> int:
    wal_name = str(args.wal_name or "").strip()
    if not WAL_NAME_RE.fullmatch(wal_name):
        raise SystemExit(f"Invalid WAL filename: {wal_name}")
    destination = Path(args.destination)
    config = load_config()
    client = build_client(config)
    key = _wal_key(config, wal_name)
    head = client.head_object(Bucket=config.bucket, Key=key)
    try:
        expected_size = int(head["ContentLength"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"PITR WAL metadata is incomplete: {wal_name}") from exc
    expected_sha256 = artifact_security.object_sha256(
        client,
        bucket=config.bucket,
        key=key,
        expected_size=expected_size,
    )
    artifact_security.download_verified_object(
        client,
        bucket=config.bucket,
        key=key,
        destination=destination,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
    )
    print(json.dumps({"status": "fetched", "wal_name": wal_name, "key": key}, sort_keys=True))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare an isolated PostgreSQL PITR restore from private S3/R2."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_cmd = subparsers.add_parser("list-basebackups", help="List validated manifests")
    list_cmd.set_defaults(func=command_list)

    prepare = subparsers.add_parser(
        "prepare",
        help="Download and extract a basebackup into an empty restore directory",
    )
    prepare.add_argument("--target-dir", required=True)
    prepare.add_argument("--backup-id", default="")
    prepare.add_argument("--target-time", default="")
    prepare.add_argument("--target-name", default="")
    prepare.add_argument("--target-lsn", default="")
    prepare.add_argument("--expected-system-identifier", required=True)
    prepare.add_argument("--required-end-wal", required=True)
    prepare.add_argument(
        "--wal-mode",
        choices=("local", "remote"),
        default="local",
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
    )
    prepare.add_argument(
        "--min-free-bytes",
        type=int,
        default=int(os.getenv("PITR_RESTORE_MIN_FREE_BYTES", str(DEFAULT_MIN_FREE_BYTES))),
    )
    prepare.add_argument("--restore-mount-path", default="/pitr-restore")
    prepare.add_argument(
        "--restore-helper-path",
        default="/app/scripts/ha/restore_postgres_pitr_from_s3.py",
    )
    prepare.set_defaults(func=command_prepare)

    fetch_wal = subparsers.add_parser("fetch-wal", help="Fetch one verified WAL file")
    fetch_wal.add_argument("--wal-name", required=True)
    fetch_wal.add_argument("--destination", required=True)
    fetch_wal.set_defaults(func=command_fetch_wal)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
