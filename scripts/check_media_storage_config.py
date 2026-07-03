#!/usr/bin/env python3
"""Validate runtime media storage targets without printing secrets."""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.general_media_storage_service import get_general_media_storage
from services.media_storage_service import (
    get_product_media_storage,
    get_product_original_source_storage,
)


OBJECT_STORAGE_PROVIDERS = {"r2", "s3", "s3_compatible"}
SAMPLE_HASH = "a" * 64
WRITE_PROBE_CONTENT = b"mvn-media-storage-write-probe\n"


@dataclass(frozen=True)
class MediaStorageCheck:
    label: str
    provider: str
    target_url: str
    target_path: str


def build_checks() -> list[MediaStorageCheck]:
    general_storage = get_general_media_storage(require_write=False)
    general_target = general_storage.build_media_object(
        content_hash=SAMPLE_HASH,
        namespace="orders/121/telegram",
        variant_type="photo",
        extension="jpg",
        size_bytes=1,
    )

    product_storage = get_product_media_storage(require_write=False)
    product_target = product_storage.build_product_variant_object(
        content_hash=SAMPLE_HASH,
        variant_type="original",
        extension="webp",
    )

    original_storage = get_product_original_source_storage()
    original_target = original_storage.build_product_original_object(
        content_hash=SAMPLE_HASH,
        extension="webp",
    )

    return [
        MediaStorageCheck(
            label="general_media",
            provider=general_target.storage_provider,
            target_url=general_target.url,
            target_path=general_target.path,
        ),
        MediaStorageCheck(
            label="product_variants",
            provider=product_target.storage_provider,
            target_url=product_target.url,
            target_path=product_target.path,
        ),
        MediaStorageCheck(
            label="product_originals",
            provider=original_target.storage_provider,
            target_url=original_target.url,
            target_path=original_target.path,
        ),
    ]


def validate_checks(
    checks: list[MediaStorageCheck],
    *,
    require_object_storage: bool,
    expected_public_base_url: str,
) -> list[str]:
    failures: list[str] = []
    normalized_public_base = expected_public_base_url.strip().rstrip("/")

    for check in checks:
        if require_object_storage and check.provider not in OBJECT_STORAGE_PROVIDERS:
            failures.append(
                f"{check.label} provider is {check.provider!r}; expected one of "
                f"{', '.join(sorted(OBJECT_STORAGE_PROVIDERS))}"
            )

        parsed = urlparse(check.target_url)
        if require_object_storage and parsed.scheme not in {"http", "https"}:
            failures.append(f"{check.label} target_url is not a public CDN URL: {check.target_url}")

        if normalized_public_base and not check.target_url.startswith(f"{normalized_public_base}/"):
            failures.append(
                f"{check.label} target_url does not start with {normalized_public_base}: "
                f"{check.target_url}"
            )

    return failures


async def run_write_probe() -> list[str]:
    failures: list[str] = []
    probes = [
        (
            "general_media",
            get_general_media_storage(require_write=True).save_media(
                content=WRITE_PROBE_CONTENT,
                namespace="diagnostics/media-storage",
                variant_type="probe",
                extension="txt",
                content_type="text/plain",
            ),
        ),
        (
            "product_variants",
            get_product_media_storage(require_write=True).save_product_variant(
                content=WRITE_PROBE_CONTENT,
                variant_type="diagnostics",
                extension="txt",
            ),
        ),
        (
            "product_originals",
            get_product_original_source_storage().save_product_original(
                content=WRITE_PROBE_CONTENT,
                extension="txt",
            ),
        ),
    ]
    for label, awaitable in probes:
        try:
            stored = await awaitable
        except Exception as exc:
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
            print(
                "media_storage_write_probe "
                f"label={label} "
                "status=failed "
                f"error_type={type(exc).__name__} "
                f"error={exc}",
                file=sys.stderr,
            )
            continue
        print(
            "media_storage_write_probe "
            f"label={label} "
            "status=passed "
            f"provider={stored.storage_provider} "
            f"url={stored.url} "
            f"path={stored.path}"
        )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate configured media storage providers and public target URLs."
    )
    parser.add_argument(
        "--require-object-storage",
        action="store_true",
        help="Fail unless all media classes target R2/S3-compatible object storage.",
    )
    parser.add_argument(
        "--expected-public-base-url",
        default="",
        help="Optional expected public URL prefix, for example https://cdn.mvn.by.",
    )
    parser.add_argument(
        "--write-probe",
        action="store_true",
        help="Also try writing one small diagnostic object through each storage adapter.",
    )
    args = parser.parse_args(argv)

    try:
        checks = build_checks()
    except Exception as exc:
        print(
            f"media_storage_config_status=error error_type={type(exc).__name__} error={exc}",
            file=sys.stderr,
        )
        return 1

    for check in checks:
        print(
            "media_storage_target "
            f"label={check.label} "
            f"provider={check.provider} "
            f"url={check.target_url} "
            f"path={check.target_path}"
        )

    failures = validate_checks(
        checks,
        require_object_storage=args.require_object_storage,
        expected_public_base_url=args.expected_public_base_url,
    )
    if failures:
        for failure in failures:
            print(f"media_storage_config_failure={failure}", file=sys.stderr)
        return 1

    if args.write_probe:
        write_failures = asyncio.run(run_write_probe())
        if write_failures:
            return 1

    print("media_storage_config_status=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
