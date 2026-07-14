import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts/ha/verify_patroni_release_image.py"
)
SPEC = importlib.util.spec_from_file_location("verify_patroni_release_image", MODULE_PATH)
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verify
SPEC.loader.exec_module(verify)


def _manifest(*, platform=None, attestation=True):
    runtime_digest = f"sha256:{'1' * 64}"
    descriptors = [
        {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": runtime_digest,
            "size": 100,
            "platform": platform or {"architecture": "amd64", "os": "linux"},
        }
    ]
    if attestation:
        descriptors.append(
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": f"sha256:{'2' * 64}",
                "size": 80,
                "platform": {"architecture": "unknown", "os": "unknown"},
                "annotations": {
                    "vnd.docker.reference.type": "attestation-manifest",
                    "vnd.docker.reference.digest": runtime_digest,
                },
            }
        )
    return json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": descriptors,
        },
        separators=(",", ":"),
    ).encode()


def _digest(raw):
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def test_manifest_requires_exact_digest_amd64_runtime_and_linked_attestation():
    raw = _manifest()
    parsed = verify.verify_manifest(raw, _digest(raw))

    assert len(parsed["manifests"]) == 2

    with pytest.raises(verify.VerificationError, match="digest"):
        verify.verify_manifest(raw, f"sha256:{'0' * 64}")
    arm = _manifest(platform={"architecture": "arm64", "os": "linux"})
    with pytest.raises(verify.VerificationError, match="linux/amd64"):
        verify.verify_manifest(arm, _digest(arm))
    unattested = _manifest(attestation=False)
    with pytest.raises(verify.VerificationError, match="no BuildKit attestation"):
        verify.verify_manifest(unattested, _digest(unattested))


def test_provenance_requires_exact_source_and_revision():
    provenance = {
        "SLSA": {
            "buildDefinition": {
                "externalParameters": {
                    "request": {
                        "root": {
                            "configSource": {
                                "request": {
                                    "args": {
                                        "vcs:source": "https://github.com/mvnby/air-api.git",
                                        "vcs:revision": "a" * 40,
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "runDetails": {"builder": {"id": "buildkit"}},
        }
    }

    verify.verify_provenance(
        provenance,
        expected_source="https://github.com/mvnby/air-api",
        expected_revision="a" * 40,
    )
    with pytest.raises(verify.VerificationError, match="revision"):
        verify.verify_provenance(
            provenance,
            expected_source="https://github.com/mvnby/air-api",
            expected_revision="b" * 40,
        )


def test_sbom_requires_nonempty_spdx_packages():
    valid = {
        "SPDX": {
            "SPDXID": "SPDXRef-DOCUMENT",
            "spdxVersion": "SPDX-2.3",
            "packages": [{"SPDXID": "SPDXRef-Package-postgresql"}],
        }
    }
    verify.verify_sbom(valid)

    valid["SPDX"]["packages"] = []
    with pytest.raises(verify.VerificationError, match="no packages"):
        verify.verify_sbom(valid)


def test_manifest_evidence_preserves_exact_registry_bytes(tmp_path):
    payload = b'{"schemaVersion":2}'
    target = tmp_path / "manifest.json"

    verify._write_raw(target, payload)

    assert target.read_bytes() == payload
    assert _digest(target.read_bytes()) == _digest(payload)
