#!/usr/bin/env python3
"""Immutable S3 storage contracts and bounded verification of PITR representations."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class S3UploadConfig(Protocol):
    bucket: str


def _is_missing_object_error(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error")
    code = str(error.get("Code") or "") if isinstance(error, dict) else ""
    metadata = response.get("ResponseMetadata")
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return code in {"404", "NoSuchKey", "NotFound"} or status == 404


def _is_precondition_failed(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error")
    code = str(error.get("Code") or "") if isinstance(error, dict) else ""
    metadata = response.get("ResponseMetadata")
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return code in {"PreconditionFailed", "ConditionalRequestConflict"} or status in {
        409,
        412,
    }


def _head_optional(client, *, bucket: str, key: str):
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except BaseException as exc:
        if _is_missing_object_error(exc):
            return None
        raise


def _require_remote_contract(
    head,
    *,
    key: str,
    size_bytes: int,
    sha256: str,
    extra_metadata: dict | None = None,
) -> None:
    metadata = head.get("Metadata") or {}
    try:
        remote_size = int(head["ContentLength"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"PITR object metadata is incomplete: {key}") from exc
    if (
        remote_size != size_bytes
        or metadata.get("sha256") != sha256
        or metadata.get("uploaded-by") != "mvn-postgres-pitr"
        or any(metadata.get(k) != v for k, v in (extra_metadata or {}).items())
    ):
        raise RuntimeError(f"Refusing to overwrite a different PITR object: {key}")


def _verify_remote_content(
    client,
    *,
    bucket: str,
    key: str,
    size_bytes: int,
    sha256: str,
) -> None:
    response = client.get_object(Bucket=bucket, Key=key)
    try:
        response_size = int(response["ContentLength"])
        body = response["Body"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"PITR object response is incomplete: {key}") from exc
    try:
        if response_size != size_bytes:
            raise RuntimeError(f"PITR object response size mismatch: {key}")
        digest = hashlib.sha256()
        received = 0
        while received <= size_bytes:
            chunk = body.read(min(1024 * 1024, size_bytes + 1 - received))
            if not chunk:
                break
            if isinstance(chunk, str):
                chunk = chunk.encode()
            received += len(chunk)
            if received > size_bytes:
                raise RuntimeError(f"PITR object exceeds its declared size: {key}")
            digest.update(chunk)
        if body.read(1):
            raise RuntimeError(f"PITR object exceeds its declared size: {key}")
        if received != size_bytes or digest.hexdigest() != sha256:
            raise RuntimeError(f"PITR object content verification failed: {key}")
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()


def _verify_remote_object(
    client,
    *,
    bucket: str,
    key: str,
    size_bytes: int,
    sha256: str,
    head=None,
    extra_metadata: dict | None = None,
) -> None:
    contract = head or client.head_object(Bucket=bucket, Key=key)
    _require_remote_contract(
        contract,
        key=key,
        size_bytes=size_bytes,
        sha256=sha256,
        extra_metadata=extra_metadata,
    )
    if extra_metadata and extra_metadata.get("wal-codec") == "gzip":
        # Upload success must prove exactly the representation accepted by
        # restore, including version/ETag identity and both byte streams.
        read_gzip_wal(client, bucket=bucket, key=key, head=contract)
        return
    _verify_remote_content(
        client,
        bucket=bucket,
        key=key,
        size_bytes=size_bytes,
        sha256=sha256,
    )
    if extra_metadata:
        _require_remote_contract(
            client.head_object(Bucket=bucket, Key=key), key=key,
            size_bytes=size_bytes, sha256=sha256, extra_metadata=extra_metadata,
        )


def _object_write_kwargs(*, config: S3UploadConfig, key: str, digest: str) -> dict:
    return {
        "Bucket": config.bucket,
        "Key": key,
        "ContentType": "application/octet-stream",
        "CacheControl": "private, max-age=0, no-store",
        "Metadata": {
            "sha256": digest,
            "uploaded-by": "mvn-postgres-pitr",
        },
    }


def _read_exact_part(descriptor: int, size_bytes: int) -> bytes:
    payload = bytearray()
    while len(payload) < size_bytes:
        chunk = os.read(descriptor, size_bytes - len(payload))
        if not chunk:
            raise RuntimeError("PITR multipart source ended unexpectedly")
        payload.extend(chunk)
    return bytes(payload)


def upload_create_only(
    client,
    *,
    config: S3UploadConfig,
    key: str,
    descriptor: int,
    size_bytes: int,
    digest: str,
    multipart_threshold_bytes: int,
    multipart_part_bytes: int,
    max_multipart_parts: int,
    extra_metadata: dict | None = None,
) -> None:
    common = _object_write_kwargs(config=config, key=key, digest=digest)
    common["Metadata"].update(extra_metadata or {})
    os.lseek(descriptor, 0, os.SEEK_SET)
    if size_bytes <= multipart_threshold_bytes:
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            client.put_object(
                **common,
                Body=stream,
                ContentLength=size_bytes,
                IfNoneMatch="*",
            )
        return

    response = client.create_multipart_upload(**common)
    upload_id = response.get("UploadId") if isinstance(response, dict) else None
    if not isinstance(upload_id, str) or not upload_id:
        raise RuntimeError("PITR multipart upload did not return an upload ID")
    completed = False
    try:
        parts = []
        remaining = size_bytes
        part_number = 1
        while remaining:
            if part_number > max_multipart_parts:
                raise RuntimeError("PITR artifact requires too many multipart chunks")
            part_size = min(multipart_part_bytes, remaining)
            payload = _read_exact_part(descriptor, part_size)
            uploaded = client.upload_part(
                Bucket=config.bucket,
                Key=key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=payload,
                ContentLength=part_size,
            )
            etag = uploaded.get("ETag") if isinstance(uploaded, dict) else None
            if not isinstance(etag, str) or not etag:
                raise RuntimeError("PITR multipart upload returned an invalid part ETag")
            parts.append({"ETag": etag, "PartNumber": part_number})
            remaining -= part_size
            part_number += 1
        client.complete_multipart_upload(
            Bucket=config.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
            IfNoneMatch="*",
        )
        completed = True
    finally:
        if not completed:
            try:
                client.abort_multipart_upload(
                    Bucket=config.bucket,
                    Key=key,
                    UploadId=upload_id,
                )
            except BaseException:
                pass


WAL_NAME_RE = re.compile(r"^[0-9A-F]{24}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_WAL_BYTES = 1024**3
STREAM_CHUNK_BYTES = 1024**2


@dataclass(frozen=True)
class GzipWalContract:
    filename: str
    stored_size: int
    stored_sha256: str
    original_size: int
    original_sha256: str


def wal_storage_name(filename: str) -> tuple[str, str]:
    """Parse storage suffix without confusing it with PostgreSQL's WAL name."""
    if filename.endswith(".gz") and WAL_NAME_RE.fullmatch(filename[:-3]):
        return filename[:-3], "gzip"
    if re.fullmatch(r"[0-9A-F]{8}\.history\..+", filename):
        raise SystemExit(f"Unsupported WAL storage codec: {filename}")
    if len(filename) > 24 and WAL_NAME_RE.fullmatch(filename[:24]):
        suffix = filename[24:]
        if suffix not in {".partial", ""} and not re.fullmatch(r"\.[0-9A-F]{8}\.backup", suffix):
            raise SystemExit(f"Unsupported WAL storage codec: {filename}")
    return filename, "raw"


def gzip_wal_contract(head: dict, *, key: str) -> GzipWalContract:
    metadata = head.get("Metadata") or {}
    name, codec = wal_storage_name(key.rsplit("/", 1)[-1])
    original = metadata.get("wal-size", "")
    stored = head.get("ContentLength")
    if (
        codec != "gzip"
        or metadata.get("wal-format") != "1"
        or metadata.get("wal-codec") != "gzip"
        or metadata.get("wal-name") != name
        or metadata.get("uploaded-by") != "mvn-postgres-pitr"
        or not isinstance(original, str)
        or not re.fullmatch(r"[1-9][0-9]{0,9}", original)
        or not 1024**2 <= int(original) <= MAX_WAL_BYTES
        or int(original) & (int(original) - 1)
        or type(stored) is not int
        or not 0 < stored <= int(original) + int(original) // 1000 + 1024
        or not isinstance(metadata.get("sha256"), str)
        or not SHA256_RE.fullmatch(metadata["sha256"])
        or not isinstance(metadata.get("wal-sha256"), str)
        or not SHA256_RE.fullmatch(metadata["wal-sha256"])
        or head.get("VersionId") not in (None, "null")
        or not isinstance(head.get("ETag"), str)
        or not head["ETag"]
    ):
        raise SystemExit(f"Invalid compressed WAL contract: {key}")
    return GzipWalContract(name, stored, metadata["sha256"], int(original), metadata["wal-sha256"])


def wal_head_identity(head: dict) -> tuple:
    return (head.get("ContentLength"), head.get("ETag"), head.get("VersionId"),
            tuple(sorted((head.get("Metadata") or {}).items())))


def read_gzip_wal(client, *, bucket: str, key: str, head: dict, output=None) -> bytes:
    """Verify both byte streams, returning the original long header in bounded memory."""
    contract = gzip_wal_contract(head, key=key)
    response = client.get_object(Bucket=bucket, Key=key, IfMatch=head["ETag"])
    body = response["Body"]
    try:
        if (response.get("ContentLength") != contract.stored_size
            or response.get("ETag") != head["ETag"]
            or response.get("VersionId") not in (None, "null")):
            raise SystemExit(f"Compressed WAL response identity mismatch: {key}")
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        stored_digest, original_digest = hashlib.sha256(), hashlib.sha256()
        received = written = 0
        header = bytearray()
        while received <= contract.stored_size:
            chunk = body.read(min(STREAM_CHUNK_BYTES, contract.stored_size + 1 - received))
            if not chunk:
                break
            received += len(chunk)
            if received > contract.stored_size:
                raise SystemExit(f"Compressed WAL exceeds its declared size: {key}")
            stored_digest.update(chunk)
            pending = chunk
            while pending:
                decoded = decoder.decompress(pending, min(STREAM_CHUNK_BYTES, contract.original_size + 1 - written))
                written += len(decoded)
                if written > contract.original_size:
                    raise SystemExit(f"Decoded WAL exceeds its declared size: {key}")
                original_digest.update(decoded)
                header.extend(decoded[:max(0, 40 - len(header))])
                if output is not None:
                    output.write(decoded)
                if decoder.unused_data:
                    raise SystemExit(f"Compressed WAL has trailing data or multiple members: {key}")
                pending = decoder.unconsumed_tail
        if (body.read(1) or received != contract.stored_size or not decoder.eof
            or written != contract.original_size
            or stored_digest.hexdigest() != contract.stored_sha256
            or original_digest.hexdigest() != contract.original_sha256):
            raise SystemExit(f"Compressed WAL content verification failed: {key}")
        if wal_head_identity(client.head_object(Bucket=bucket, Key=key)) != wal_head_identity(head):
            raise SystemExit(f"Compressed WAL identity changed during read: {key}")
        return bytes(header)
    except zlib.error as exc:
        raise SystemExit(f"Invalid gzip WAL payload: {key}") from exc
    finally:
        body.close()


def download_gzip_wal(client, *, bucket: str, key: str, head: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    root = destination.parent.resolve()
    if destination.resolve().parent != root:
        raise SystemExit(f"Unsafe PITR object destination: {destination.name}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            read_gzip_wal(client, bucket=bucket, key=key, head=head, output=output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
