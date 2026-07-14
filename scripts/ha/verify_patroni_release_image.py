#!/usr/bin/env python3
"""Verify immutable Patroni OCI release evidence from the registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


IMMUTABLE_IMAGE_RE = re.compile(
    r"^ghcr\.io/[a-z0-9._/-]+/patroni@(?P<digest>sha256:[0-9a-f]{64})$"
)
ATTESTATION_TYPE = "attestation-manifest"


class VerificationError(RuntimeError):
    """Release metadata failed a required invariant."""


def _run(command: list[str]) -> bytes:
    try:
        completed = subprocess.run(command, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", b"") or b""
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise VerificationError(f"command failed: {' '.join(command)}: {detail}") from exc
    return completed.stdout


def _load_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{label} must be a JSON object")
    return value


def _values_for_key(value: Any, wanted: str) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == wanted and isinstance(child, str):
                found.append(child)
            found.extend(_values_for_key(child, wanted))
    elif isinstance(value, list):
        for child in value:
            found.extend(_values_for_key(child, wanted))
    return found


def _normalize_source(value: str) -> str:
    normalized = value.removeprefix("git+").rstrip("/")
    return normalized.removesuffix(".git")


def verify_manifest(raw: bytes, expected_digest: str) -> dict[str, Any]:
    actual_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if actual_digest != expected_digest:
        raise VerificationError(
            f"registry manifest digest {actual_digest} differs from {expected_digest}"
        )
    manifest = _load_json(raw, "top-level manifest")
    if manifest.get("schemaVersion") != 2:
        raise VerificationError("top-level manifest must use schemaVersion 2")
    if manifest.get("mediaType") != "application/vnd.oci.image.index.v1+json":
        raise VerificationError("top-level manifest must be an OCI image index")
    descriptors = manifest.get("manifests")
    if not isinstance(descriptors, list) or not descriptors:
        raise VerificationError("top-level image index has no descriptors")

    runtime: list[dict[str, Any]] = []
    attestations: list[dict[str, Any]] = []
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            raise VerificationError("image descriptor must be an object")
        annotations = descriptor.get("annotations") or {}
        if annotations.get("vnd.docker.reference.type") == ATTESTATION_TYPE:
            attestations.append(descriptor)
        else:
            runtime.append(descriptor)

    if len(runtime) != 1:
        raise VerificationError("image index must contain exactly one runtime descriptor")
    platform = runtime[0].get("platform")
    if platform != {"architecture": "amd64", "os": "linux"}:
        raise VerificationError("runtime descriptor must be exactly linux/amd64")
    if runtime[0].get("mediaType") != "application/vnd.oci.image.manifest.v1+json":
        raise VerificationError("runtime descriptor must reference an OCI image manifest")
    runtime_digest = runtime[0].get("digest")
    if not isinstance(runtime_digest, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", runtime_digest
    ):
        raise VerificationError("runtime descriptor digest is invalid")
    if not attestations:
        raise VerificationError("image index has no BuildKit attestation descriptor")
    for item in attestations:
        if item.get("mediaType") != "application/vnd.oci.image.manifest.v1+json":
            raise VerificationError("attestation descriptor must reference an OCI manifest")
        if item.get("platform") != {"architecture": "unknown", "os": "unknown"}:
            raise VerificationError("attestation descriptor platform is invalid")
        if (item.get("annotations") or {}).get(
            "vnd.docker.reference.digest"
        ) != runtime_digest:
            raise VerificationError("attestation is not linked to the runtime descriptor")
    return manifest


def verify_provenance(
    provenance: dict[str, Any], *, expected_source: str, expected_revision: str
) -> None:
    slsa = provenance.get("SLSA")
    if not isinstance(slsa, dict):
        raise VerificationError("BuildKit SLSA provenance is missing")
    if not isinstance(slsa.get("buildDefinition"), dict) or not isinstance(
        slsa.get("runDetails"), dict
    ):
        raise VerificationError("BuildKit SLSA provenance is incomplete")

    sources = {_normalize_source(item) for item in _values_for_key(slsa, "vcs:source")}
    revisions = set(_values_for_key(slsa, "vcs:revision"))
    normalized_expected_source = _normalize_source(expected_source)
    if sources != {normalized_expected_source}:
        raise VerificationError(
            f"provenance source is not exactly {normalized_expected_source}"
        )
    if revisions != {expected_revision}:
        raise VerificationError(
            f"provenance revision is not exactly {expected_revision}"
        )


def verify_sbom(sbom: dict[str, Any]) -> None:
    spdx = sbom.get("SPDX")
    if not isinstance(spdx, dict):
        raise VerificationError("SPDX SBOM is missing")
    if spdx.get("SPDXID") != "SPDXRef-DOCUMENT":
        raise VerificationError("SPDX document identifier is invalid")
    if not str(spdx.get("spdxVersion", "")).startswith("SPDX-"):
        raise VerificationError("SPDX version is missing")
    packages = spdx.get("packages")
    if not isinstance(packages, list) or not packages:
        raise VerificationError("SPDX SBOM has no packages")


def verify_release_image(
    image: str, *, expected_source: str, expected_revision: str
) -> tuple[bytes, bytes, bytes]:
    match = IMMUTABLE_IMAGE_RE.fullmatch(image)
    if match is None:
        raise VerificationError("image must be an immutable GHCR Patroni digest reference")

    manifest_raw = _run(["docker", "buildx", "imagetools", "inspect", image, "--raw"])
    verify_manifest(manifest_raw, match.group("digest"))
    provenance_raw = _run(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            image,
            "--format",
            "{{json .Provenance}}",
        ]
    )
    verify_provenance(
        _load_json(provenance_raw, "provenance"),
        expected_source=expected_source,
        expected_revision=expected_revision,
    )
    sbom_raw = _run(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            image,
            "--format",
            "{{json .SBOM}}",
        ]
    )
    verify_sbom(_load_json(sbom_raw, "SBOM"))
    return manifest_raw, provenance_raw, sbom_raw


def _write(path: Path, payload: bytes) -> None:
    path.write_bytes(payload.rstrip(b"\n") + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--provenance-out", type=Path, required=True)
    parser.add_argument("--sbom-out", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest, provenance, sbom = verify_release_image(
            args.image,
            expected_source=args.expected_source,
            expected_revision=args.expected_revision,
        )
    except VerificationError as exc:
        print(f"Patroni release image verification failed: {exc}")
        return 1
    _write(args.manifest_out, manifest)
    _write(args.provenance_out, provenance)
    _write(args.sbom_out, sbom)
    print("Patroni release image manifest, linux/amd64 runtime, provenance, and SBOM passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
