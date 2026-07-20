#!/usr/bin/env python3
"""Check private S3/R2 PostgreSQL PITR objects without printing secrets."""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


build_client, load_config = _load_upload_helpers()

WAL_SEGMENT_RE = re.compile(r"^[0-9A-F]{24}$")
REMOTE_WAL_SEGMENT_RE = re.compile(r"^[0-9A-F]{24}(?:\.partial)?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SYSTEM_IDENTIFIER_RE = re.compile(r"^[1-9][0-9]{15,19}$")
BACKUP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
LSN_RE = re.compile(r"^[0-9A-F]{1,8}/[0-9A-F]{1,8}$")
UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SOURCE_NODES = {"mvn-api", "zakup"}
EXPECTED_UPLOADER = "mvn-postgres-pitr"
WAL_SEGMENT_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_MANIFEST_CLOCK_SKEW = timedelta(minutes=5)
MAX_MANIFEST_FILES = 128
MAX_LIST_PAGES = 256
MAX_LIST_OBJECTS = 100_000
MANIFEST_FIELDS = {
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
MANIFEST_FILE_FIELDS = {"name", "key", "size_bytes", "sha256"}


class StatusProofError(RuntimeError):
    """A remote object did not satisfy the reviewed PITR proof contract."""


@dataclass(frozen=True)
class ManifestProof:
    backup_id: str
    completed_at: datetime
    file_count: int
    system_identifier: str
    timeline: int


def _latest_object(
    client: Any, bucket: str, prefix: str, suffix: str = "", *, canonical_wal: bool = False
) -> dict[str, Any] | None:
    paginator = client.get_paginator("list_objects_v2")
    latest: dict[str, Any] | None = None
    pages = 0
    objects = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        pages += 1
        if pages > MAX_LIST_PAGES:
            raise StatusProofError("remote object listing exceeded the page limit")
        contents = page.get("Contents", [])
        if not isinstance(contents, list):
            raise StatusProofError("remote object listing is malformed")
        objects += len(contents)
        if objects > MAX_LIST_OBJECTS:
            raise StatusProofError("remote object listing exceeded the object limit")
        for item in contents:
            if not isinstance(item, dict):
                raise StatusProofError("remote object listing contains a malformed item")
            key = str(item.get("Key") or "")
            if suffix and not key.endswith(suffix):
                continue
            filename = key.rsplit("/", 1)[-1]
            if canonical_wal and (
                not REMOTE_WAL_SEGMENT_RE.fullmatch(filename)
                or key != f"{prefix}{filename[:8]}/{filename}"
            ):
                continue
            if canonical_wal:
                size = item.get("Size")
                if (
                    isinstance(size, bool)
                    or not isinstance(size, int)
                    or size != WAL_SEGMENT_BYTES
                ):
                    raise StatusProofError("remote WAL segment size is not canonical")
            if key.endswith("/"):
                continue
            last_modified = item.get("LastModified")
            if not key or not isinstance(last_modified, datetime):
                raise StatusProofError("remote object listing metadata is incomplete")
            if latest is None or last_modified > latest["LastModified"]:
                latest = item
            elif (
                last_modified == latest["LastModified"]
                and key != str(latest.get("Key") or "")
            ):
                raise StatusProofError("remote latest object is ambiguous")
    return latest


def _is_missing_object_error(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error")
    code = str(error.get("Code") or "") if isinstance(error, dict) else ""
    metadata = response.get("ResponseMetadata")
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return code in {"404", "NoSuchKey", "NotFound"} or status == 404


def _object_head_proof(
    head: dict[str, Any],
    *,
    label: str,
    expected_size: int | None = None,
    maximum_size: int | None = None,
) -> tuple[int, str]:
    if not isinstance(head, dict):
        raise StatusProofError(f"{label} HEAD response is malformed")
    raw_size = head.get("ContentLength")
    if isinstance(raw_size, bool):
        raise StatusProofError(f"{label} size is invalid")
    try:
        size = int(raw_size)
    except (TypeError, ValueError) as exc:
        raise StatusProofError(f"{label} size is invalid") from exc
    if expected_size is not None and size != expected_size:
        raise StatusProofError(f"{label} size is not canonical")
    if maximum_size is not None and not 0 < size <= maximum_size:
        raise StatusProofError(f"{label} exceeds the bounded size contract")
    metadata = head.get("Metadata")
    if not isinstance(metadata, dict):
        raise StatusProofError(f"{label} metadata is missing")
    digest = str(metadata.get("sha256") or "")
    if not SHA256_RE.fullmatch(digest):
        raise StatusProofError(f"{label} sha256 metadata is invalid")
    if metadata.get("uploaded-by") != EXPECTED_UPLOADER:
        raise StatusProofError(f"{label} provenance is invalid")
    return size, digest


def _read_body_bounded(body: Any, *, expected_size: int) -> bytes:
    if not hasattr(body, "read"):
        raise StatusProofError("basebackup manifest body is unreadable")
    payload = bytearray()
    try:
        while len(payload) <= MAX_MANIFEST_BYTES:
            chunk = body.read(min(64 * 1024, MAX_MANIFEST_BYTES + 1 - len(payload)))
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise StatusProofError("basebackup manifest body is not bytes")
            payload.extend(chunk)
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()
    if len(payload) != expected_size or len(payload) > MAX_MANIFEST_BYTES:
        raise StatusProofError("basebackup manifest body size does not match HEAD")
    return bytes(payload)


def _strict_json_object(raw_payload: bytes) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if not isinstance(key, str) or key in result:
                raise StatusProofError("basebackup manifest has duplicate keys")
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise StatusProofError("basebackup manifest contains a non-JSON number")

    try:
        payload = json.loads(
            raw_payload.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatusProofError("basebackup manifest is not canonical JSON") from exc
    if not isinstance(payload, dict):
        raise StatusProofError("basebackup manifest is not an object")
    return payload


def _lsn_value(value: Any) -> int:
    if not isinstance(value, str) or not LSN_RE.fullmatch(value):
        raise StatusProofError("basebackup manifest LSN is invalid")
    high, low = value.split("/", 1)
    numeric = (int(high, 16) << 32) | int(low, 16)
    if value != f"{numeric >> 32:X}/{numeric & 0xFFFFFFFF:X}":
        raise StatusProofError("basebackup manifest LSN is not canonical")
    return numeric


def _utc_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not UTC_TIMESTAMP_RE.fullmatch(value):
        raise StatusProofError(f"basebackup manifest {label} is not canonical UTC")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise StatusProofError(f"basebackup manifest {label} is invalid") from exc


def _validate_manifest(
    payload: dict[str, Any],
    *,
    manifest_key: str,
    key_prefix: str,
    cluster: str,
    expected_system_identifier: str,
) -> ManifestProof:
    if set(payload) != MANIFEST_FIELDS:
        raise StatusProofError("basebackup manifest top-level schema is invalid")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise StatusProofError("basebackup manifest schema version is invalid")
    backup_id = payload["backup_id"]
    if not isinstance(backup_id, str) or not BACKUP_ID_RE.fullmatch(backup_id):
        raise StatusProofError("basebackup manifest backup id is invalid")
    expected_manifest_key = (
        f"{key_prefix}/{cluster}/basebackups/{backup_id}/manifest.json"
    )
    if manifest_key != expected_manifest_key:
        raise StatusProofError("basebackup manifest key is not canonical")
    if payload["cluster"] != cluster:
        raise StatusProofError("basebackup manifest cluster does not match")
    if payload["system_identifier"] != expected_system_identifier:
        raise StatusProofError("basebackup manifest system identifier does not match")
    timeline = payload["timeline"]
    if type(timeline) is not int or not 0 < timeline <= 0xFFFFFFFF:
        raise StatusProofError("basebackup manifest timeline is invalid")
    if _lsn_value(payload["end_lsn"]) < _lsn_value(payload["start_lsn"]):
        raise StatusProofError("basebackup manifest LSN range is reversed")
    started_at = _utc_timestamp(payload["started_at"], label="start time")
    completed_at = _utc_timestamp(payload["completed_at"], label="completion time")
    if completed_at < started_at:
        raise StatusProofError("basebackup manifest completion precedes its start")
    if completed_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise StatusProofError("basebackup manifest completion time is in the future")
    if (
        not isinstance(payload["source_node"], str)
        or payload["source_node"] not in SOURCE_NODES
    ):
        raise StatusProofError("basebackup manifest source node is invalid")

    files = payload["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_MANIFEST_FILES:
        raise StatusProofError("basebackup manifest file list is invalid")
    names: set[str] = set()
    keys: set[str] = set()
    file_prefix = f"{key_prefix}/{cluster}/basebackups/{backup_id}/"
    for item in files:
        if not isinstance(item, dict) or set(item) != MANIFEST_FILE_FIELDS:
            raise StatusProofError("basebackup manifest file schema is invalid")
        name = item["name"]
        key = item["key"]
        size = item["size_bytes"]
        digest = item["sha256"]
        if (
            not isinstance(name, str)
            or not FILE_NAME_RE.fullmatch(name)
            or name == "manifest.json"
            or name in names
        ):
            raise StatusProofError("basebackup manifest file name is invalid")
        if not isinstance(key, str) or key != f"{file_prefix}{name}" or key in keys:
            raise StatusProofError("basebackup manifest file key is not canonical")
        if type(size) is not int or not 0 < size <= 0x7FFFFFFFFFFFFFFF:
            raise StatusProofError("basebackup manifest file size is invalid")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise StatusProofError("basebackup manifest file sha256 is invalid")
        names.add(name)
        keys.add(key)
    if not {"base.tar.gz", "backup_manifest"}.issubset(names):
        raise StatusProofError("basebackup manifest lacks required PostgreSQL artifacts")
    return ManifestProof(
        backup_id=backup_id,
        completed_at=completed_at,
        file_count=len(files),
        system_identifier=expected_system_identifier,
        timeline=timeline,
    )


def _load_manifest_proof(
    client: Any,
    *,
    bucket: str,
    key: str,
    key_prefix: str,
    cluster: str,
    expected_system_identifier: str,
) -> tuple[ManifestProof, int]:
    head = client.head_object(Bucket=bucket, Key=key)
    expected_size, expected_digest = _object_head_proof(
        head,
        label="basebackup manifest",
        maximum_size=MAX_MANIFEST_BYTES,
    )
    last_modified = head.get("LastModified")
    if (
        not isinstance(last_modified, datetime)
        or last_modified.tzinfo is None
        or last_modified.utcoffset() is None
    ):
        raise StatusProofError("basebackup manifest LastModified is invalid")
    last_modified = last_modified.astimezone(timezone.utc)
    response = client.get_object(Bucket=bucket, Key=key)
    if not isinstance(response, dict):
        raise StatusProofError("basebackup manifest GET response is malformed")
    raw_response_size = response.get("ContentLength")
    if isinstance(raw_response_size, bool):
        raise StatusProofError("basebackup manifest GET size is invalid")
    try:
        response_size = int(raw_response_size)
    except (TypeError, ValueError) as exc:
        raise StatusProofError("basebackup manifest GET size is invalid") from exc
    if response_size != expected_size:
        raise StatusProofError("basebackup manifest GET size does not match HEAD")
    raw_payload = _read_body_bounded(response.get("Body"), expected_size=expected_size)
    if hashlib.sha256(raw_payload).hexdigest() != expected_digest:
        raise StatusProofError("basebackup manifest body sha256 does not match metadata")
    proof = _validate_manifest(
        _strict_json_object(raw_payload),
        manifest_key=key,
        key_prefix=key_prefix,
        cluster=cluster,
        expected_system_identifier=expected_system_identifier,
    )
    publish_delay = last_modified - proof.completed_at
    if publish_delay < -MAX_MANIFEST_CLOCK_SKEW:
        raise StatusProofError(
            "basebackup manifest LastModified predates its completion time beyond clock skew"
        )
    return proof, expected_size


def _age_hours(last_modified: datetime) -> float:
    if last_modified.tzinfo is None:
        last_modified = last_modified.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - last_modified).total_seconds() / 3600)


def _print_manifest_status(
    proof: ManifestProof,
    *,
    key: str,
    size_bytes: int,
    max_age_hours: float,
) -> str:
    age_hours = _age_hours(proof.completed_at)
    status = "fresh" if age_hours <= max_age_hours else "stale"
    print(
        f"pitr_remote_basebackup status={status} "
        f"age_hours={age_hours:.2f} max_age_hours={max_age_hours:g} "
        f"key={key} size_bytes={size_bytes} files={proof.file_count} "
        f"timeline={proof.timeline} system_identifier={proof.system_identifier}"
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
    parser.add_argument("--expected-system-identifier", default="")
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
        expected_system_identifier = str(
            args.expected_system_identifier or ""
        ).strip()
        if not SYSTEM_IDENTIFIER_RE.fullmatch(expected_system_identifier):
            print("pitr_remote_basebackup status=invalid_expected_system_identifier")
            failures += 1
        else:
            try:
                latest_basebackup = _latest_object(
                    client,
                    config.bucket,
                    base_prefix,
                    suffix="/manifest.json",
                )
                if latest_basebackup is None:
                    print(f"pitr_remote_basebackup status=missing prefix={base_prefix}")
                    failures += 1
                else:
                    manifest_key = str(latest_basebackup["Key"])
                    proof, manifest_size = _load_manifest_proof(
                        client,
                        bucket=config.bucket,
                        key=manifest_key,
                        key_prefix=config.key_prefix,
                        cluster=config.cluster,
                        expected_system_identifier=expected_system_identifier,
                    )
                    if _print_manifest_status(
                        proof,
                        key=manifest_key,
                        size_bytes=manifest_size,
                        max_age_hours=args.max_basebackup_age_hours,
                    ) != "fresh":
                        failures += 1
            except StatusProofError as exc:
                print(f"pitr_remote_basebackup status=invalid reason={exc}")
                failures += 1
            except Exception:
                print(
                    "pitr_remote_basebackup "
                    "status=invalid reason=remote_request_failed"
                )
                failures += 1

    if not args.skip_wal:
        expected_wal = str(args.expected_wal or "").strip().upper()
        expected_wal_present = False
        expected_wal_item: dict[str, Any] | None = None
        local_pending_wal_count = args.local_pending_wal_count
        if args.local_pending_wal_count is not None and args.local_pending_wal_count < 0:
            print(
                "pitr_remote_wal status=invalid_pending_count "
                f"local_pending_wal_count={args.local_pending_wal_count}"
            )
            failures += 1
            local_pending_wal_count = None
        if not expected_wal:
            print("pitr_remote_wal_expected status=missing_argument")
            failures += 1
        elif not WAL_SEGMENT_RE.fullmatch(expected_wal):
            print(f"pitr_remote_wal_expected status=invalid wal={expected_wal}")
            failures += 1
        else:
            expected_key = f"{wal_prefix}{expected_wal[:8]}/{expected_wal}"
            try:
                expected_head = client.head_object(
                    Bucket=config.bucket,
                    Key=expected_key,
                )
            except Exception as exc:
                if not _is_missing_object_error(exc):
                    print(
                        "pitr_remote_wal_expected status=invalid "
                        f"wal={expected_wal} reason=head_failed"
                    )
                    failures += 1
                else:
                    print(
                        "pitr_remote_wal_expected status=missing "
                        f"wal={expected_wal} key={expected_key}"
                    )
                    failures += 1
            else:
                try:
                    expected_size, expected_digest = _object_head_proof(
                        expected_head,
                        label="expected WAL",
                        expected_size=WAL_SEGMENT_BYTES,
                    )
                except StatusProofError as exc:
                    print(
                        "pitr_remote_wal_expected status=invalid "
                        f"wal={expected_wal} key={expected_key} reason={exc}"
                    )
                    failures += 1
                else:
                    last_modified = expected_head.get("LastModified")
                    if (
                        not isinstance(last_modified, datetime)
                        or last_modified.tzinfo is None
                        or last_modified.utcoffset() is None
                        or last_modified.astimezone(timezone.utc)
                        > datetime.now(timezone.utc) + timedelta(minutes=5)
                    ):
                        print(
                            "pitr_remote_wal_expected status=invalid "
                            f"wal={expected_wal} key={expected_key} "
                            "reason=last_modified_missing"
                        )
                        failures += 1
                        expected_wal_present = False
                        expected_wal_item = None
                    else:
                        expected_wal_present = True
                        expected_wal_item = {
                            "Key": expected_key,
                            "LastModified": last_modified,
                            "Size": expected_size,
                        }
                        print(
                            "pitr_remote_wal_expected status=present "
                            f"wal={expected_wal} key={expected_key} "
                            f"size_bytes={expected_size} sha256={expected_digest} "
                            f"uploaded_by={EXPECTED_UPLOADER}"
                        )
        try:
            latest_wal = expected_wal_item or _latest_object(
                client,
                config.bucket,
                wal_prefix,
                canonical_wal=True,
            )
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
        except StatusProofError as exc:
            print(f"pitr_remote_wal status=invalid reason={exc}")
            failures += 1
        except Exception:
            print("pitr_remote_wal status=invalid reason=remote_request_failed")
            failures += 1

    print(
        f"pitr_remote_summary status={'failed' if failures else 'passed'} "
        f"failures={failures} warnings={warnings}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
