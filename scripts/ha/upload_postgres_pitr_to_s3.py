#!/usr/bin/env python3
"""Upload PostgreSQL PITR artifacts to a private S3-compatible bucket.

This is intended to run from the backend image, which already includes boto3.
It deliberately requires POSTGRES_PITR_* variables and does not fall back to
public product-media R2 credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import secrets
import stat
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

ARCHIVABLE_WAL_NAME_RE = re.compile(
    r"^(?:[0-9A-F]{24}(?:\.partial)?|[0-9A-F]{24}\.[0-9A-F]{8}\.backup|[0-9A-F]{8}\.history)$"
)
PARTIAL_WAL_NAME_RE = re.compile(r"^[0-9A-F]{24}\.partial$")
WAL_SEGMENT_BYTES = 16 * 1024 * 1024
BACKUP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TRANSACTION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SYSTEM_IDENTIFIER_RE = re.compile(r"^[1-9][0-9]{15,19}$")
LSN_RE = re.compile(r"^[0-9A-F]{1,8}/[0-9A-F]{1,8}$")
UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PROBE_NODES = {"mvn-api", "zakup"}
MULTIPART_THRESHOLD_BYTES = 64 * 1024**2
MULTIPART_PART_BYTES = 64 * 1024**2
MAX_MULTIPART_PARTS = 10_000
MAX_CONDITIONAL_OBJECT_BYTES = MULTIPART_PART_BYTES * MAX_MULTIPART_PARTS


def _load_immutable_upload_helpers():
    explicit = os.getenv("POSTGRES_PITR_IMMUTABLE_UPLOAD_HELPER", "").strip()
    if explicit:
        helper_path = Path(explicit)
        if not helper_path.is_absolute() or not helper_path.is_file():
            raise SystemExit("Explicit PITR immutable upload helper is invalid")
        module_name = "mvn_postgres_pitr_immutable_upload"
        specification = importlib.util.spec_from_file_location(module_name, helper_path)
        if specification is None or specification.loader is None:
            loader = importlib.machinery.SourceFileLoader(module_name, str(helper_path))
            specification = importlib.util.spec_from_loader(module_name, loader)
        if specification is None or specification.loader is None:
            raise SystemExit("Explicit PITR immutable upload helper could not be loaded")
        module = importlib.util.module_from_spec(specification)
        sys.modules[specification.name] = module
        specification.loader.exec_module(module)
        return module
    try:
        from scripts.ha import postgres_pitr_immutable_upload

        return postgres_pitr_immutable_upload
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Could not load PITR immutable upload helper. Run from the repo root "
            "or set POSTGRES_PITR_IMMUTABLE_UPLOAD_HELPER."
        ) from exc


immutable_upload = _load_immutable_upload_helpers()
_head_optional = immutable_upload._head_optional
_is_missing_object_error = immutable_upload._is_missing_object_error
_is_precondition_failed = immutable_upload._is_precondition_failed
_object_write_kwargs = immutable_upload._object_write_kwargs
_read_exact_part = immutable_upload._read_exact_part
_require_remote_contract = immutable_upload._require_remote_contract
_verify_remote_content = immutable_upload._verify_remote_content
_verify_remote_object = immutable_upload._verify_remote_object


@dataclass(frozen=True)
class PitrS3Config:
    bucket: str
    endpoint_url: str
    region: str
    access_key_id: str
    secret_access_key: str
    key_prefix: str
    cluster: str


@dataclass(frozen=True)
class ArtifactSnapshot:
    path: Path
    device: int
    inode: int
    size_bytes: int
    mode: int
    link_count: int
    mtime_ns: int
    ctime_ns: int
    sha256: str


@dataclass(frozen=True)
class BasebackupLineage:
    system_identifier: str
    timeline: int
    start_lsn: str
    end_lsn: str
    started_at: str
    completed_at: str
    source_node: str


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


def _snapshot(path: Path, metadata: os.stat_result, digest: str = "") -> ArtifactSnapshot:
    return ArtifactSnapshot(
        path=path,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        size_bytes=metadata.st_size,
        mode=metadata.st_mode,
        link_count=metadata.st_nlink,
        mtime_ns=metadata.st_mtime_ns,
        ctime_ns=metadata.st_ctime_ns,
        sha256=digest,
    )


def _assert_regular_single_link(path: Path, metadata: os.stat_result) -> None:
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise RuntimeError(f"PITR artifact must be a regular single-link file: {path}")


@contextmanager
def _open_artifact(path: Path) -> Iterator[tuple[int, ArtifactSnapshot]]:
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("required PITR artifact protection is unavailable")
    before = path.lstat()
    _assert_regular_single_link(path, before)
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        _assert_regular_single_link(path, opened)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError(f"PITR artifact changed while it was opened: {path}")
        yield descriptor, _snapshot(path, opened)
    finally:
        os.close(descriptor)


def _sha256_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    with os.fdopen(os.dup(descriptor), "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def _assert_snapshot_unchanged(
    expected: ArtifactSnapshot,
    metadata: os.stat_result,
) -> None:
    actual = _snapshot(expected.path, metadata)
    if (
        actual.device,
        actual.inode,
        actual.size_bytes,
        actual.mode,
        actual.link_count,
        actual.mtime_ns,
        actual.ctime_ns,
    ) != (
        expected.device,
        expected.inode,
        expected.size_bytes,
        expected.mode,
        expected.link_count,
        expected.mtime_ns,
        expected.ctime_ns,
    ):
        raise RuntimeError(f"PITR artifact changed during upload: {expected.path}")


def sha256_file(path: Path) -> str:
    with _open_artifact(path) as (descriptor, expected):
        digest = _sha256_fd(descriptor)
        _assert_snapshot_unchanged(expected, os.fstat(descriptor))
        return digest


def iter_wal_files(archive_dir: Path) -> Iterable[Path]:
    for path in sorted(archive_dir.iterdir()):
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_nlink == 1
            and ARCHIVABLE_WAL_NAME_RE.fullmatch(path.name)
        ):
            if PARTIAL_WAL_NAME_RE.fullmatch(path.name) and metadata.st_size != WAL_SEGMENT_BYTES:
                raise RuntimeError(f"partial WAL segment size is not canonical: {path}")
            yield path


def wal_key(config: PitrS3Config, filename: str) -> str:
    timeline = filename[:8]
    return f"{config.key_prefix}/{config.cluster}/wal/{timeline}/{filename}"


def basebackup_key(config: PitrS3Config, backup_id: str, filename: str) -> str:
    return f"{config.key_prefix}/{config.cluster}/basebackups/{backup_id}/{filename}"


def _lsn_value(value: str) -> int:
    if not LSN_RE.fullmatch(value):
        raise SystemExit(f"PITR basebackup LSN is not canonical: {value!r}")
    high, low = value.split("/", 1)
    numeric = (int(high, 16) << 32) | int(low, 16)
    if value != f"{numeric >> 32:X}/{numeric & 0xFFFFFFFF:X}":
        raise SystemExit(f"PITR basebackup LSN is not canonical: {value!r}")
    return numeric


def _utc_timestamp(value: str, *, label: str) -> datetime:
    if not UTC_TIMESTAMP_RE.fullmatch(value):
        raise SystemExit(f"PITR basebackup {label} is not canonical UTC")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise SystemExit(f"PITR basebackup {label} is invalid") from exc
    return parsed


def _basebackup_lineage(args: argparse.Namespace) -> BasebackupLineage:
    system_identifier = str(args.system_identifier or "")
    if not SYSTEM_IDENTIFIER_RE.fullmatch(system_identifier):
        raise SystemExit("PITR basebackup system identifier is invalid")
    try:
        timeline = int(args.timeline)
    except (TypeError, ValueError) as exc:
        raise SystemExit("PITR basebackup timeline is invalid") from exc
    if not 0 < timeline <= 0xFFFFFFFF or str(timeline) != str(args.timeline):
        raise SystemExit("PITR basebackup timeline is invalid")
    start_lsn = str(args.start_lsn or "")
    end_lsn = str(args.end_lsn or "")
    if _lsn_value(end_lsn) < _lsn_value(start_lsn):
        raise SystemExit("PITR basebackup end LSN precedes start LSN")
    started_at = str(args.started_at or "")
    completed_at = str(args.completed_at or "")
    if _utc_timestamp(completed_at, label="completion time") < _utc_timestamp(
        started_at, label="start time"
    ):
        raise SystemExit("PITR basebackup completion time precedes start time")
    source_node = str(args.source_node or "")
    if source_node not in PROBE_NODES:
        raise SystemExit("PITR basebackup source node is invalid")
    return BasebackupLineage(
        system_identifier=system_identifier,
        timeline=timeline,
        start_lsn=start_lsn,
        end_lsn=end_lsn,
        started_at=started_at,
        completed_at=completed_at,
        source_node=source_node,
    )


def _upload_create_only(
    client,
    *,
    config: PitrS3Config,
    key: str,
    descriptor: int,
    size_bytes: int,
    digest: str,
) -> None:
    immutable_upload.upload_create_only(
        client,
        config=config,
        key=key,
        descriptor=descriptor,
        size_bytes=size_bytes,
        digest=digest,
        multipart_threshold_bytes=MULTIPART_THRESHOLD_BYTES,
        multipart_part_bytes=MULTIPART_PART_BYTES,
        max_multipart_parts=MAX_MULTIPART_PARTS,
    )


def upload_file(
    client,
    config: PitrS3Config,
    source: Path,
    key: str,
    dry_run: bool,
    *,
    conditional_create: bool = True,
) -> ArtifactSnapshot:
    with _open_artifact(source) as (descriptor, opened):
        digest = _sha256_fd(descriptor)
        expected = ArtifactSnapshot(**{**opened.__dict__, "sha256": digest})
        if not conditional_create:
            raise RuntimeError("mutable PITR object upload is disabled")
        if expected.size_bytes > MAX_CONDITIONAL_OBJECT_BYTES:
            raise RuntimeError(
                "PITR artifact exceeds the reviewed conditional multipart capacity"
            )
        if dry_run:
            print(
                json.dumps(
                    {"action": "dry_run_upload", "key": key, "path": str(source)}
                )
            )
            _assert_snapshot_unchanged(expected, os.fstat(descriptor))
        else:
            existing = _head_optional(client, bucket=config.bucket, key=key)
            if existing is not None:
                _verify_remote_object(
                    client,
                    bucket=config.bucket,
                    key=key,
                    size_bytes=expected.size_bytes,
                    sha256=digest,
                    head=existing,
                )
            else:
                try:
                    _upload_create_only(
                        client,
                        config=config,
                        key=key,
                        descriptor=descriptor,
                        size_bytes=expected.size_bytes,
                        digest=digest,
                    )
                except BaseException as exc:
                    if not _is_precondition_failed(exc):
                        raise
                _assert_snapshot_unchanged(expected, os.fstat(descriptor))
                _verify_remote_object(
                    client,
                    bucket=config.bucket,
                    key=key,
                    size_bytes=expected.size_bytes,
                    sha256=digest,
                )
        return expected


def _unlink_uploaded_artifact(snapshot: ArtifactSnapshot) -> None:
    current = snapshot.path.lstat()
    _assert_regular_single_link(snapshot.path, current)
    _assert_snapshot_unchanged(snapshot, current)
    snapshot.path.unlink()


def upload_wal(args: argparse.Namespace) -> int:
    config = load_config()
    archive_dir = Path(args.archive_dir)
    if not archive_dir.is_dir():
        raise SystemExit(f"WAL archive dir does not exist: {archive_dir}")

    client = build_client(config)
    uploaded = 0
    for path in iter_wal_files(archive_dir):
        key = wal_key(config, path.name)
        snapshot = upload_file(
            client,
            config,
            path,
            key,
            args.dry_run,
            conditional_create=True,
        )
        uploaded += 1
        print(
            json.dumps(
                {
                    "action": "uploaded_wal" if not args.dry_run else "planned_wal",
                    "filename": path.name,
                    "key": key,
                    "size_bytes": snapshot.size_bytes,
                },
                sort_keys=True,
            )
        )
        if args.delete_after_upload and not args.dry_run:
            _unlink_uploaded_artifact(snapshot)

    print(json.dumps({"kind": "wal", "count": uploaded}, sort_keys=True))
    return 0


def iter_basebackup_files(source_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(source_dir.iterdir()):
        if path.name.startswith("."):
            continue
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
            files.append(path)
    return files


def upload_basebackup(args: argparse.Namespace) -> int:
    config = load_config()
    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        raise SystemExit(f"Basebackup dir does not exist: {source_dir}")

    backup_id = args.backup_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not BACKUP_ID_RE.fullmatch(backup_id):
        raise SystemExit("PITR basebackup id is invalid")
    lineage = _basebackup_lineage(args)
    files = iter_basebackup_files(source_dir)
    if not files:
        raise SystemExit(f"No basebackup files found in {source_dir}")

    client = build_client(config)
    manifest = {
        "schema_version": 1,
        "backup_id": backup_id,
        "cluster": config.cluster,
        "system_identifier": lineage.system_identifier,
        "timeline": lineage.timeline,
        "start_lsn": lineage.start_lsn,
        "end_lsn": lineage.end_lsn,
        "started_at": lineage.started_at,
        "completed_at": lineage.completed_at,
        "source_node": lineage.source_node,
        "files": [],
    }

    for path in files:
        key = basebackup_key(config, backup_id, path.name)
        snapshot = upload_file(client, config, path, key, args.dry_run)
        manifest["files"].append(
            {
                "name": path.name,
                "key": key,
                "size_bytes": snapshot.size_bytes,
                "sha256": snapshot.sha256,
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
                    "size_bytes": snapshot.size_bytes,
                },
                sort_keys=True,
            )
        )

    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_key = basebackup_key(config, backup_id, "manifest.json")
    if args.dry_run:
        print(json.dumps({"action": "dry_run_manifest", "key": manifest_key}))
    else:
        existing = _head_optional(
            client,
            bucket=config.bucket,
            key=manifest_key,
        )
        if existing is None:
            try:
                client.put_object(
                    Bucket=config.bucket,
                    Key=manifest_key,
                    Body=manifest_bytes,
                    ContentLength=len(manifest_bytes),
                    ContentType="application/json",
                    CacheControl="private, max-age=0, no-store",
                    Metadata={
                        "sha256": manifest_digest,
                        "uploaded-by": "mvn-postgres-pitr",
                    },
                    IfNoneMatch="*",
                )
            except BaseException as exc:
                if not _is_precondition_failed(exc):
                    raise
        _verify_remote_object(
            client,
            bucket=config.bucket,
            key=manifest_key,
            size_bytes=len(manifest_bytes),
            sha256=manifest_digest,
            head=existing,
        )

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


def probe_credentials(args: argparse.Namespace) -> int:
    if not TRANSACTION_ID_RE.fullmatch(args.transaction_id):
        raise SystemExit("PITR credential probe transaction id is invalid")
    if args.node not in PROBE_NODES:
        raise SystemExit("PITR credential probe node is invalid")
    config = load_config()
    client = build_client(config)
    payload = secrets.token_bytes(64)
    digest = hashlib.sha256(payload).hexdigest()
    key = (
        f"{config.key_prefix}/{config.cluster}/probes/"
        f"{args.transaction_id}/{args.node}/{secrets.token_hex(16)}"
    )
    put_succeeded = False
    try:
        client.put_object(
            Bucket=config.bucket,
            Key=key,
            Body=payload,
            ContentType="application/octet-stream",
            CacheControl="private, max-age=0, no-store",
            Metadata={
                "sha256": digest,
                "uploaded-by": "mvn-postgres-pitr-probe",
            },
        )
        put_succeeded = True
        head = client.head_object(Bucket=config.bucket, Key=key)
        if (
            int(head.get("ContentLength", -1)) != len(payload)
            or (head.get("Metadata") or {}).get("sha256") != digest
        ):
            raise RuntimeError("PITR credential probe HEAD verification failed")
        response = client.get_object(Bucket=config.bucket, Key=key)
        body = response.get("Body")
        if body is None:
            raise RuntimeError("PITR credential probe GET response has no body")
        try:
            downloaded = body.read(len(payload) + 1)
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()
        if downloaded != payload:
            raise RuntimeError("PITR credential probe GET verification failed")
    finally:
        if put_succeeded:
            client.delete_object(Bucket=config.bucket, Key=key)
    try:
        client.head_object(Bucket=config.bucket, Key=key)
    except BaseException as exc:
        if not _is_missing_object_error(exc):
            raise
    else:
        raise RuntimeError("PITR credential probe object remained after delete")
    print(
        json.dumps(
            {
                "kind": "credential_probe",
                "node": args.node,
                "status": "passed",
                "transaction_id": args.transaction_id,
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
    basebackup.add_argument("--system-identifier", required=True)
    basebackup.add_argument("--timeline", required=True)
    basebackup.add_argument("--start-lsn", required=True)
    basebackup.add_argument("--end-lsn", required=True)
    basebackup.add_argument("--started-at", required=True)
    basebackup.add_argument("--completed-at", required=True)
    basebackup.add_argument(
        "--source-node", choices=tuple(sorted(PROBE_NODES)), required=True
    )
    basebackup.add_argument("--dry-run", action="store_true")
    basebackup.set_defaults(func=upload_basebackup)

    probe = subparsers.add_parser(
        "probe", help="Prove candidate credentials with put/head/get/delete"
    )
    probe.add_argument("--transaction-id", required=True)
    probe.add_argument("--node", choices=tuple(sorted(PROBE_NODES)), required=True)
    probe.set_defaults(func=probe_credentials)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
