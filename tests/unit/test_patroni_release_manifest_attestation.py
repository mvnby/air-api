import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.unit.test_patroni_candidate_transactions import (
    PATRONI_RUNNER,
    _patroni_runner_env,
)


def _manifest(env):
    return Path(env["PATRONI_FINALIZED_RELEASE_MANIFEST"])


def _read_manifest(path):
    return json.loads(path.read_text(encoding="ascii"))


def _write_manifest(path, value):
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    path.chmod(0o600)


def _run_guard_failure(env, project):
    canonical = (project / "compose.yml").read_bytes()
    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert (project / "compose.yml").read_bytes() == canonical
    assert not (project / "compose.yml.candidate").exists()
    assert not Path(env["CHILD_LOG"]).exists()
    assert not Path(env["RECONCILE_LOG"]).exists()
    assert not Path(env["PATRONI_ROLE_AGENT_TARGET"]).exists()
    assert not Path(env["VOICE_SYNC_LOG"]).exists()
    assert not Path(env["SYSTEMCTL_LOG"]).read_text(encoding="utf-8")
    return result


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "corrupt",
        "noncanonical",
        "wrong-project",
        "wrong-path",
        "wrong-entry-mode",
        "wrong-compose-digest",
        "wrong-release-digest",
        "other-asset-mode",
        "other-asset-content",
        "duplicate-path",
        "unsorted-paths",
        "unsafe-manifest-mode",
        "symlink",
        "hardlink",
    ],
)
def test_candidate_requires_exact_finalized_release_manifest(
    tmp_path,
    damage,
):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    path = _manifest(env)
    manifest = _read_manifest(path)
    compose_entry = next(
        item
        for item in manifest["files"]
        if item["path"] == str(project / "compose.yml")
    )
    other_entry = next(
        item
        for item in manifest["files"]
        if item["path"] != str(project / "compose.yml")
    )

    if damage == "missing":
        path.unlink()
    elif damage == "corrupt":
        path.write_text("{", encoding="ascii")
    elif damage == "noncanonical":
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    elif damage == "wrong-project":
        manifest["project_dir"] = str(tmp_path / "other-project")
        _write_manifest(path, manifest)
    elif damage == "wrong-path":
        compose_entry["path"] = str(project / "other-compose.yml")
        _write_manifest(path, manifest)
    elif damage == "wrong-entry-mode":
        compose_entry["mode"] = 0o755
        _write_manifest(path, manifest)
    elif damage == "wrong-compose-digest":
        compose_entry["sha256"] = "0" * 64
        _write_manifest(path, manifest)
    elif damage == "wrong-release-digest":
        manifest["release_sha256"] = "0" * 64
        _write_manifest(path, manifest)
    elif damage == "other-asset-mode":
        Path(other_entry["path"]).chmod(0o700)
    elif damage == "other-asset-content":
        Path(other_entry["path"]).write_bytes(b"tampered release tool\n")
    elif damage == "duplicate-path":
        manifest["files"].append(dict(compose_entry))
        _write_manifest(path, manifest)
    elif damage == "unsorted-paths":
        manifest["files"].insert(
            0,
            {
                "mode": 0o644,
                "path": str(project / "z-last"),
                "sha256": "2" * 64,
            },
        )
        _write_manifest(path, manifest)
    elif damage == "unsafe-manifest-mode":
        path.chmod(0o644)
    elif damage == "symlink":
        target = tmp_path / "manifest-target.json"
        path.replace(target)
        path.symlink_to(target)
    elif damage == "hardlink":
        os.link(path, tmp_path / "manifest-hardlink.json")

    result = _run_guard_failure(env, project)
    assert "finalized PITR release" in result.stderr


def test_candidate_rejects_release_manifest_wrong_group(tmp_path):
    alternate_group = next(
        (group for group in os.getgroups() if group != os.getegid()),
        None,
    )
    if alternate_group is None:
        pytest.skip("current user has no alternate group for metadata test")
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    path = _manifest(env)
    os.chown(path, -1, alternate_group)

    result = _run_guard_failure(env, project)

    assert "current-user-and-group-owned" in result.stderr


def test_candidate_accepts_canonical_finalized_manifest(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (project / "compose.yml.candidate").exists()
