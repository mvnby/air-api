#!/usr/bin/env python3
"""Bounded, path-safe handling for untrusted remote PITR artifacts."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO


MAX_MANIFEST_FILES = 64
MAX_MANIFEST_FILE_BYTES = 4 * 1024**4
MAX_POSTGRES_MANIFEST_BYTES = 256 * 1024 * 1024
MAX_TAR_MEMBERS = 10_000_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BACKUP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SYSTEM_IDENTIFIER_RE = re.compile(r"^[1-9][0-9]{15,19}$")
RESTORE_POINT_RE = re.compile(r"^mvn_pitr_[0-9a-f]{32}$")
LSN_RE = re.compile(r"^[0-9A-F]{1,8}/[0-9A-F]{1,8}$")
UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SOURCE_NODES = frozenset({"mvn-api", "zakup"})
OUTER_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "backup_id",
        "cluster",
        "system_identifier",
        "timeline",
        "start_lsn",
        "end_lsn",
        "started_at",
        "completed_at",
        "source_node",
        "files",
    }
)
OUTER_FILE_KEYS = frozenset({"name", "key", "size_bytes", "sha256"})
LEGACY_V0_MANIFEST_KEYS = frozenset(
    {"backup_id", "created_at", "cluster", "hostname", "files"}
)
POSTGRES_WAL_RANGE_KEYS = frozenset({"Timeline", "Start-LSN", "End-LSN"})


@dataclass(frozen=True)
class ManifestFile:
    name: str
    key: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class BasebackupManifest:
    backup_id: str
    started_at: datetime
    completed_at: datetime
    key: str
    payload: dict[str, Any]
    system_identifier: str
    timeline: int
    start_lsn: str
    end_lsn: str
    files: tuple[ManifestFile, ...]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verify_optional_digest(payload: bytes, metadata: dict[str, Any], *, label: str) -> None:
    digest = str((metadata.get("Metadata") or {}).get("sha256") or "")
    if digest and (not SHA256_RE.fullmatch(digest) or sha256_bytes(payload) != digest):
        raise SystemExit(f"{label} digest mismatch")


def estimated_extracted_bytes(postgres_manifest: dict[str, Any]) -> int:
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


def ensure_restore_space(
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
    required_bytes = basebackup_bytes + extracted_bytes + wal_bytes + min_free_bytes
    if available_bytes < required_bytes:
        raise SystemExit(
            "Insufficient free space for PITR prepare: "
            f"available_bytes={available_bytes} required_bytes={required_bytes} "
            f"basebackup_bytes={basebackup_bytes} extracted_bytes={extracted_bytes} "
            f"wal_bytes={wal_bytes} reserve_bytes={min_free_bytes}"
        )
    return available_bytes, required_bytes


def ensure_empty_target_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise SystemExit(f"Target directory must be empty: {path}")


def validate_legacy_v0_manifest(
    *,
    payload: dict[str, Any],
    manifest_key: str,
    key_prefix: str,
    cluster: str,
) -> None:
    """Validate the exact historical schema before omitting it from restore."""
    if set(payload) != set(LEGACY_V0_MANIFEST_KEYS):
        raise SystemExit("Unversioned basebackup manifest is not exact historical v0")
    backup_id = payload["backup_id"]
    created_at = payload["created_at"]
    hostname = payload["hostname"]
    raw_files = payload["files"]
    if not isinstance(backup_id, str) or not BACKUP_ID_RE.fullmatch(backup_id):
        raise SystemExit("Historical v0 basebackup ID is invalid")
    prefix = f"{key_prefix}/{cluster}/basebackups/{backup_id}"
    if payload["cluster"] != cluster or manifest_key != f"{prefix}/manifest.json":
        raise SystemExit("Historical v0 basebackup identity is not canonical")
    if not isinstance(created_at, str) or not 20 <= len(created_at) <= 40:
        raise SystemExit("Historical v0 basebackup timestamp is invalid")
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit("Historical v0 basebackup timestamp is invalid") from exc
    if parsed_created_at.tzinfo is None or parsed_created_at.utcoffset() != timezone.utc.utcoffset(None):
        raise SystemExit("Historical v0 basebackup timestamp is not UTC")
    if (
        not isinstance(hostname, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}", hostname)
    ):
        raise SystemExit("Historical v0 basebackup hostname is invalid")
    if not isinstance(raw_files, list) or len(raw_files) > MAX_MANIFEST_FILES:
        raise SystemExit("Historical v0 basebackup file list is invalid")
    names: set[str] = set()
    for raw in raw_files:
        if not isinstance(raw, dict) or set(raw) != set(OUTER_FILE_KEYS):
            raise SystemExit("Historical v0 basebackup file schema is invalid")
        name = raw["name"]
        size_bytes = raw["size_bytes"]
        if (
            not isinstance(name, str)
            or not name
            or name in {".", "..", "manifest.json"}
            or "/" in name
            or "\\" in name
            or Path(name).name != name
            or name in names
        ):
            raise SystemExit("Historical v0 basebackup filename is invalid")
        if raw["key"] != f"{prefix}/{name}":
            raise SystemExit("Historical v0 basebackup object key is not canonical")
        if not isinstance(raw["sha256"], str) or not SHA256_RE.fullmatch(raw["sha256"]):
            raise SystemExit("Historical v0 basebackup digest is invalid")
        if (
            isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or not 0 <= size_bytes <= MAX_MANIFEST_FILE_BYTES
        ):
            raise SystemExit("Historical v0 basebackup file size is invalid")
        names.add(name)


def validate_manifest_files(
    *,
    payload: dict[str, Any],
    manifest_key: str,
    backup_id: str,
    key_prefix: str,
    cluster: str,
) -> tuple[ManifestFile, ...]:
    raw_files = payload.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise SystemExit(f"Basebackup manifest has no files: {manifest_key}")
    if len(raw_files) > MAX_MANIFEST_FILES:
        raise SystemExit(f"Basebackup manifest has too many files: {manifest_key}")
    if not BACKUP_ID_RE.fullmatch(backup_id):
        raise SystemExit(f"Basebackup manifest has invalid backup_id: {backup_id!r}")
    if payload.get("backup_id") != backup_id:
        raise SystemExit("Basebackup manifest backup_id is not canonical")
    if payload.get("cluster") != cluster:
        raise SystemExit("Basebackup manifest cluster does not match PITR configuration")
    prefix = f"{key_prefix}/{cluster}/basebackups/{backup_id}"
    if manifest_key != f"{prefix}/manifest.json":
        raise SystemExit("Basebackup manifest key is not canonical")

    validated: list[ManifestFile] = []
    names: set[str] = set()
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise SystemExit(f"Basebackup manifest file entry is invalid: {raw!r}")
        name = raw.get("name")
        key = raw.get("key")
        digest = raw.get("sha256")
        size_bytes = raw.get("size_bytes")
        if (
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or Path(name).name != name
        ):
            raise SystemExit(f"Basebackup manifest filename is unsafe: {name!r}")
        if name in names:
            raise SystemExit(f"Basebackup manifest filename is duplicated: {name}")
        if not isinstance(key, str) or key != f"{prefix}/{name}":
            raise SystemExit(f"Basebackup manifest object key is not canonical: {name}")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise SystemExit(f"Basebackup manifest sha256 is invalid: {name}")
        if (
            isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
            or size_bytes > MAX_MANIFEST_FILE_BYTES
        ):
            raise SystemExit(f"Basebackup manifest size_bytes is invalid: {name}")
        if name == "backup_manifest" and size_bytes > MAX_POSTGRES_MANIFEST_BYTES:
            raise SystemExit("PostgreSQL backup_manifest exceeds the safety limit")
        names.add(name)
        validated.append(ManifestFile(name, key, size_bytes, digest))

    if "base.tar.gz" not in names or "backup_manifest" not in names:
        raise SystemExit("Basebackup manifest is missing required files")
    return tuple(validated)


def _require_exact_keys(value: Any, expected: frozenset[str], *, label: str) -> None:
    if not isinstance(value, dict) or set(value) != set(expected):
        raise SystemExit(f"{label} does not have the exact schema")


def parse_canonical_utc(value: Any, *, label: str) -> datetime:
    raw = value if isinstance(value, str) else ""
    if not UTC_TIMESTAMP_RE.fullmatch(raw):
        raise SystemExit(f"{label} is not canonical UTC")
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise SystemExit(f"{label} is invalid") from exc


def parse_canonical_lsn(value: Any, *, label: str) -> int:
    raw = value if isinstance(value, str) else ""
    if not LSN_RE.fullmatch(raw):
        raise SystemExit(f"{label} is not a canonical PostgreSQL LSN")
    high, low = raw.split("/", 1)
    numeric = (int(high, 16) << 32) | int(low, 16)
    if raw != f"{numeric >> 32:X}/{numeric & 0xFFFFFFFF:X}":
        raise SystemExit(f"{label} is not a canonical PostgreSQL LSN")
    return numeric


def validate_system_identifier(value: Any, *, label: str) -> str:
    raw = value if isinstance(value, str) else ""
    if not SYSTEM_IDENTIFIER_RE.fullmatch(raw):
        raise SystemExit(f"{label} is invalid")
    return raw


def validate_timeline(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= 0xFFFFFFFF:
        raise SystemExit(f"{label} is invalid")
    return value


def validate_outer_manifest(
    *,
    payload: dict[str, Any],
    manifest_key: str,
    key_prefix: str,
    cluster: str,
    expected_system_identifier: str | None,
) -> BasebackupManifest:
    _require_exact_keys(payload, OUTER_MANIFEST_KEYS, label="Basebackup manifest")
    if payload["schema_version"] != 1 or isinstance(payload["schema_version"], bool):
        raise SystemExit("Basebackup manifest schema_version must be integer 1")
    backup_id = payload["backup_id"] if isinstance(payload["backup_id"], str) else ""
    if not BACKUP_ID_RE.fullmatch(backup_id):
        raise SystemExit("Basebackup manifest backup_id is invalid")
    if payload["cluster"] != cluster:
        raise SystemExit("Basebackup manifest cluster does not match PITR configuration")
    canonical_key = f"{key_prefix}/{cluster}/basebackups/{backup_id}/manifest.json"
    if manifest_key != canonical_key:
        raise SystemExit("Basebackup manifest key is not canonical")

    system_identifier = validate_system_identifier(
        payload["system_identifier"], label="Basebackup system identifier"
    )
    if expected_system_identifier is not None and system_identifier != expected_system_identifier:
        raise SystemExit("Basebackup system identifier does not match the expected cluster")
    timeline = validate_timeline(payload["timeline"], label="Basebackup timeline")
    start_value = parse_canonical_lsn(payload["start_lsn"], label="Basebackup start LSN")
    end_value = parse_canonical_lsn(payload["end_lsn"], label="Basebackup end LSN")
    if end_value < start_value:
        raise SystemExit("Basebackup end LSN precedes start LSN")
    started_at = parse_canonical_utc(payload["started_at"], label="Basebackup start time")
    completed_at = parse_canonical_utc(
        payload["completed_at"], label="Basebackup completion time"
    )
    if completed_at < started_at:
        raise SystemExit("Basebackup completion time precedes start time")
    if not isinstance(payload["source_node"], str) or payload["source_node"] not in SOURCE_NODES:
        raise SystemExit("Basebackup source node is invalid")
    if not isinstance(payload["files"], list):
        raise SystemExit("Basebackup manifest files must be a list")
    for entry in payload["files"]:
        _require_exact_keys(entry, OUTER_FILE_KEYS, label="Basebackup file entry")
    files = validate_manifest_files(
        payload=payload,
        manifest_key=manifest_key,
        backup_id=backup_id,
        key_prefix=key_prefix,
        cluster=cluster,
    )
    return BasebackupManifest(
        backup_id=backup_id,
        started_at=started_at,
        completed_at=completed_at,
        key=manifest_key,
        payload=payload,
        system_identifier=system_identifier,
        timeline=timeline,
        start_lsn=payload["start_lsn"],
        end_lsn=payload["end_lsn"],
        files=files,
    )


def validate_postgres_manifest_lineage(
    manifest: BasebackupManifest,
    postgres_manifest: dict[str, Any],
) -> tuple[str, str]:
    raw_ranges = postgres_manifest.get("WAL-Ranges")
    if not isinstance(raw_ranges, list) or len(raw_ranges) != 1:
        raise SystemExit("PostgreSQL backup_manifest must have one WAL range")
    wal_range = raw_ranges[0]
    _require_exact_keys(
        wal_range,
        POSTGRES_WAL_RANGE_KEYS,
        label="PostgreSQL backup_manifest WAL range",
    )
    timeline = validate_timeline(
        wal_range["Timeline"], label="PostgreSQL backup_manifest timeline"
    )
    if timeline != manifest.timeline:
        raise SystemExit("PostgreSQL backup_manifest timeline does not match outer lineage")
    range_start = parse_canonical_lsn(
        wal_range["Start-LSN"], label="PostgreSQL backup_manifest start LSN"
    )
    range_end = parse_canonical_lsn(
        wal_range["End-LSN"], label="PostgreSQL backup_manifest end LSN"
    )
    if range_end < range_start:
        raise SystemExit("PostgreSQL backup_manifest WAL range is reversed")
    outer_start = parse_canonical_lsn(manifest.start_lsn, label="Basebackup start LSN")
    outer_end = parse_canonical_lsn(manifest.end_lsn, label="Basebackup end LSN")
    if outer_start > range_start or outer_end < range_end:
        raise SystemExit("Outer basebackup lineage does not bracket PostgreSQL WAL range")
    return wal_range["Start-LSN"], wal_range["End-LSN"]


def read_body_bounded(
    body: BinaryIO,
    *,
    expected_size: int,
    maximum_size: int,
    label: str,
) -> bytes:
    if expected_size < 0 or expected_size > maximum_size:
        raise SystemExit(f"{label} exceeds the safety limit")
    payload = bytearray()
    while len(payload) <= expected_size:
        chunk = body.read(min(1024 * 1024, expected_size + 1 - len(payload)))
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode()
        payload.extend(chunk)
    if len(payload) != expected_size:
        raise SystemExit(
            f"{label} size mismatch: expected {expected_size}, got {len(payload)}"
        )
    if body.read(1):
        raise SystemExit(f"{label} is larger than its declared size")
    return bytes(payload)


def _head_contract(
    client: Any,
    *,
    bucket: str,
    key: str,
    expected_size: int,
    expected_sha256: str,
) -> None:
    head = client.head_object(Bucket=bucket, Key=key)
    try:
        content_length = int(head["ContentLength"])
        remote_digest = str((head.get("Metadata") or {})["sha256"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"PITR object metadata is incomplete: {key}") from exc
    if content_length != expected_size or remote_digest != expected_sha256:
        raise SystemExit(f"PITR object metadata does not match the manifest: {key}")


def object_sha256(
    client: Any,
    *,
    bucket: str,
    key: str,
    expected_size: int,
) -> str:
    head = client.head_object(Bucket=bucket, Key=key)
    try:
        content_length = int(head["ContentLength"])
        digest = str((head.get("Metadata") or {})["sha256"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"PITR object metadata is incomplete: {key}") from exc
    if content_length != expected_size or not SHA256_RE.fullmatch(digest):
        raise SystemExit(f"PITR object metadata is invalid: {key}")
    return digest


def read_verified_object(
    client: Any,
    *,
    bucket: str,
    key: str,
    expected_size: int,
    expected_sha256: str,
    maximum_size: int,
    label: str,
) -> bytes:
    _head_contract(
        client,
        bucket=bucket,
        key=key,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
    )
    response = client.get_object(Bucket=bucket, Key=key)
    try:
        response_size = int(response["ContentLength"])
        body = response["Body"]
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"PITR object response is incomplete: {key}") from exc
    if response_size != expected_size:
        raise SystemExit(f"PITR object response size mismatch: {key}")
    payload = read_body_bounded(
        body,
        expected_size=expected_size,
        maximum_size=maximum_size,
        label=label,
    )
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise SystemExit(f"PITR object content verification failed: {key}")
    return payload


def read_bounded_object_without_digest(
    client: Any,
    *,
    bucket: str,
    key: str,
    expected_size: int,
    maximum_size: int,
    label: str,
) -> bytes:
    """Read only historical objects that predate digest metadata."""
    response = client.get_object(Bucket=bucket, Key=key)
    try:
        response_size = int(response["ContentLength"])
        body = response["Body"]
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"{label} response is incomplete: {key}") from exc
    if response_size != expected_size:
        raise SystemExit(f"{label} response size mismatch: {key}")
    return read_body_bounded(
        body,
        expected_size=expected_size,
        maximum_size=maximum_size,
        label=label,
    )


def download_verified_object(
    client: Any,
    *,
    bucket: str,
    key: str,
    destination: Path,
    expected_size: int,
    expected_sha256: str,
) -> None:
    if not SHA256_RE.fullmatch(expected_sha256):
        raise SystemExit(f"Invalid expected PITR object digest: {key}")
    _head_contract(
        client,
        bucket=bucket,
        key=key,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
    )
    response = client.get_object(Bucket=bucket, Key=key)
    try:
        response_size = int(response["ContentLength"])
        body = response["Body"]
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"PITR object response is incomplete: {key}") from exc
    if response_size != expected_size:
        raise SystemExit(f"PITR object response size mismatch: {key}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    root = destination.parent.resolve()
    if destination.resolve().parent != root:
        raise SystemExit(f"Unsafe PITR object destination: {destination.name}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    written = 0
    try:
        with os.fdopen(descriptor, "wb") as output:
            while written <= expected_size:
                chunk = body.read(min(1024 * 1024, expected_size + 1 - written))
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode()
                written += len(chunk)
                if written > expected_size:
                    raise SystemExit(f"PITR object exceeds its declared size: {key}")
                output.write(chunk)
                digest.update(chunk)
            if body.read(1):
                raise SystemExit(f"PITR object exceeds its declared size: {key}")
            output.flush()
            os.fsync(output.fileno())
        metadata = temporary.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size != expected_size
            or written != expected_size
            or digest.hexdigest() != expected_sha256
        ):
            raise SystemExit(f"PITR object content verification failed: {key}")
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_tar_member(
    member: tarfile.TarInfo,
    *,
    root: Path,
    destination: Path,
    archive_name: str,
) -> str:
    if member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE}:
        raise SystemExit(f"Unsafe tar member type in {archive_name}: {member.name}")
    member_path = (destination / member.name).resolve()
    if member_path != root and root not in member_path.parents:
        raise SystemExit(f"Unsafe tar member path in {archive_name}: {member.name}")
    return member_path.relative_to(root).as_posix() if member_path != root else "."


def safe_extract_tar_gz(
    tar_path: Path,
    destination: Path,
    *,
    max_members: int,
    max_expanded_bytes: int,
) -> None:
    if max_members <= 0 or max_members > MAX_TAR_MEMBERS:
        raise SystemExit("PITR tar member limit is invalid")
    if max_expanded_bytes < 0:
        raise SystemExit("PITR tar expanded-size limit is invalid")
    destination.mkdir(parents=True, exist_ok=True)
    destination_metadata = destination.lstat()
    if (
        destination.is_symlink()
        or not stat.S_ISDIR(destination_metadata.st_mode)
        or destination_metadata.st_nlink < 2
    ):
        raise SystemExit(f"Unsafe tar extraction destination: {destination}")
    root = destination.resolve()
    normalized_names: set[str] = set()
    count = 0
    expanded = 0
    with tarfile.open(tar_path, "r:gz") as archive:
        for member in archive:
            count += 1
            if count > max_members:
                raise SystemExit(f"Tar member limit exceeded: {tar_path.name}")
            normalized_name = _validate_tar_member(
                member,
                root=root,
                destination=destination,
                archive_name=tar_path.name,
            )
            if normalized_name in normalized_names:
                raise SystemExit(f"Duplicate normalized tar member: {member.name}")
            normalized_names.add(normalized_name)
            if member.isfile():
                if member.size < 0:
                    raise SystemExit(f"Invalid tar member size: {member.name}")
                expanded += member.size
                if expanded > max_expanded_bytes:
                    raise SystemExit(f"Tar expanded-size limit exceeded: {tar_path.name}")

    with tarfile.open(tar_path, "r:gz") as archive:
        for member in archive:
            member.uid = os.geteuid()
            member.gid = os.getegid()
            member.uname = ""
            member.gname = ""
            # Remote tar modes are untrusted and must also match the orphan
            # cleanup contract after a crash.  PGDATA needs no group/world
            # access: the restore container receives ownership explicitly.
            member.mode = 0o700 if member.isdir() else 0o600
            archive.extract(member, destination, numeric_owner=True)
            os.chmod((destination / member.name).resolve(), member.mode)
