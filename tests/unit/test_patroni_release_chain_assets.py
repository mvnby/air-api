import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = [
    ROOT / ".github/workflows/deploy.yml",
    ROOT / ".github/workflows/deploy-api-patroni.yml",
    ROOT / ".github/workflows/deploy-api-standby.yml",
    ROOT / ".github/workflows/deploy-web.yml",
    ROOT / ".github/workflows/publish-patroni-image.yml",
    ROOT / ".github/workflows/patroni-failover-rehearsal.yml",
]
SHA_ACTION = re.compile(r"^[^./][^@]*@[0-9a-f]{40}$")


def _external_uses(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "uses" and isinstance(child, str) and not child.startswith("./"):
                yield child
            yield from _external_uses(child)
    elif isinstance(value, list):
        for child in value:
            yield from _external_uses(child)


def test_reachable_production_release_actions_are_sha_pinned():
    for path in WORKFLOWS:
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        external = list(_external_uses(workflow))
        assert external, path
        assert all(SHA_ACTION.fullmatch(item) for item in external), (path, external)


def test_publish_orders_verification_rehearsal_before_sha_tag_promotion():
    path = ROOT / ".github/workflows/publish-patroni-image.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["publish"]["steps"]
    names = [step["name"] for step in steps]

    assert names.index("Verify registry manifest, provenance, and SBOM") < names.index(
        "Rehearse exact published digest"
    )
    assert names.index("Rehearse exact published digest") < names.index(
        "Upload complete pre-promotion release evidence"
    )
    assert names.index("Upload complete pre-promotion release evidence") < names.index(
        "Promote immutable digest to release SHA tag"
    )
    evidence = next(
        step
        for step in steps
        if step["name"] == "Upload complete pre-promotion release evidence"
    )
    assert evidence["with"]["if-no-files-found"] == "error"
    assert "release-manifest.json" not in evidence["with"]["path"]
    summary = next(step for step in steps if step["name"] == "Patroni release summary")
    assert summary["continue-on-error"] == "true"
    promotion = next(
        step for step in steps if step["name"] == "Promote immutable digest to release SHA tag"
    )["run"]
    assert "imagetools create --tag" in promotion
    assert "already points to" in promotion
    assert 'promoted}" != "${expected}' in promotion


def test_standalone_rehearsal_is_not_mislabelled_as_release_evidence():
    path = ROOT / ".github/workflows/patroni-failover-rehearsal.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["rehearse"]["steps"]
    summary = next(step for step in steps if step["name"] == "Rehearsal summary")["run"]

    assert "source_bound_release_evidence: false" in summary
    assert "release_evidence=true" not in summary
    assert 'REHEARSAL_RESULT}" = "success"' in summary


def test_exact_rehearsal_has_no_build_or_cached_tag_bypass():
    script = (ROOT / "scripts/ha/rehearse_patroni_failover.sh").read_text(
        encoding="utf-8"
    )

    assert "@sha256:[0-9a-f]{64}" in script
    assert "docker pull --platform linux/amd64" in script
    assert "{{.Os}}/{{.Architecture}}" in script
    assert "up -d --wait --no-build --pull never" in script
    assert "docker image inspect --format '{{.Id}}'" in script
    assert "docker inspect --format '{{.Image}}'" in script
    assert 'running_image_id}" != "${PULLED_IMAGE_ID}' in script
    assert "destination differs" in script
    assert "archive helper accepted a different-content collision" in script
    assert "00000001000000000000000A.partial" in script
    assert "count=16" in script
