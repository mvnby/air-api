#!/usr/bin/env python3
"""Create-only S3 uploads and bounded remote verification for PITR artifacts."""

from __future__ import annotations

import hashlib
import os
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


def _verify_remote_object(
    client,
    *,
    bucket: str,
    key: str,
    size_bytes: int,
    sha256: str,
    head=None,
) -> None:
    contract = head or client.head_object(Bucket=bucket, Key=key)
    _require_remote_contract(
        contract,
        key=key,
        size_bytes=size_bytes,
        sha256=sha256,
    )
    _verify_remote_content(
        client,
        bucket=bucket,
        key=key,
        size_bytes=size_bytes,
        sha256=sha256,
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
) -> None:
    common = _object_write_kwargs(config=config, key=key, digest=digest)
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
