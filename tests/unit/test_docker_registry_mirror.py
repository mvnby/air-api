import json

import pytest
import yaml

from scripts.ci.configure_docker_registry_mirror import MIRROR, configure


def test_new_config_and_repeated_setup(tmp_path):
    path = tmp_path / "docker" / "daemon.json"
    configure(path)
    first = path.read_bytes()
    configure(path)
    assert path.read_bytes() == first
    assert json.loads(first) == {"registry-mirrors": [MIRROR]}


def test_existing_options_and_other_mirrors_survive(tmp_path):
    path = tmp_path / "daemon.json"
    original = {"features": {"containerd-snapshotter": True},
                "log-driver": "local", "registry-mirrors": ["https://other.example", MIRROR]}
    path.write_text(json.dumps(original))
    configure(path)
    assert json.loads(path.read_text()) == {
        **original, "registry-mirrors": [MIRROR, "https://other.example"]}


@pytest.mark.parametrize("content", ["{invalid", "[]", '{"registry-mirrors": "bad"}', '{"registry-mirrors": [1]}'])
def test_invalid_config_is_never_overwritten(tmp_path, content):
    path = tmp_path / "daemon.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        configure(path)
    assert path.read_text() == content


def test_ci_cache_keeps_database_versions_and_pdf_renderer_digest():
    from pathlib import Path

    source = yaml.safe_load(Path("docker-compose.yml").read_text())["services"]
    ci = yaml.safe_load(Path(".github/docker-compose.ci.yml").read_text())["services"]
    for name in ["db", "db_test", "gotenberg"]:
        image = ci[name]["image"]
        assert image.startswith("mirror.gcr.io/")
        canonical = image.removeprefix("mirror.gcr.io/").removeprefix("library/")
        assert canonical == source[name]["image"]
        assert set(ci[name]) == {"image"}


@pytest.mark.parametrize("filename, count", [("ci.yml", 2), ("deploy-api-patroni.yml", 1)])
def test_builder_bootstrap_uses_verified_cached_image(filename, count):
    from pathlib import Path

    jobs = yaml.safe_load(Path(".github/workflows", filename).read_text())["jobs"]
    builders = [step for job in jobs.values() for step in job.get("steps", [])
                if step.get("uses", "").startswith("docker/setup-buildx-action@")]
    assert len(builders) == count
    for step in builders:
        assert step["with"]["driver-opts"] == (
            "image=mirror.gcr.io/moby/buildkit:buildx-stable-1@sha256:"
            "cec9f139f45e93c5c69c60f8b07cfad9f43f4ef6b6a6cd917527fea5ff2e3dea")
