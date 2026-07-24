from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import run_postgres_pitr_manual as manual
from scripts.ha import run_postgres_pitr_scheduled as scheduled
from scripts.ha.pitr_bundle_transport import BASE_REMOTE_ASSET_MODES


def _run_setup(monkeypatch, tmp_path: Path):
    project = (tmp_path / "project").resolve()
    project.mkdir()
    (project / "docker-compose.patroni.yml").write_text("services: {}\n")
    monkeypatch.setattr(
        manual, "ALLOWED_TARGETS", {str(project): "docker-compose.patroni.yml"}
    )
    monkeypatch.setattr(manual.os, "geteuid", lambda: 0)
    monkeypatch.setattr(manual, "_validate_self", lambda: None)
    monkeypatch.setattr(manual, "_reject_maintenance_marker", lambda: None)
    monkeypatch.setattr(manual, "REQUIRED_HELPERS", ())
    attestations = []
    monkeypatch.setattr(
        manual,
        "_attest_finalized_release",
        lambda project_dir, compose_file, **kwargs: attestations.append(
            (project_dir, compose_file, kwargs["expected_release_sha256"])
        ),
    )
    lock_paths = []

    def open_lock(path=manual.LOCK_PATH):
        lock_paths.append(path)
        return os.open(tmp_path / f"lock-{len(lock_paths)}", os.O_CREAT | os.O_RDWR, 0o600)

    monkeypatch.setattr(manual, "_open_lock", open_lock)
    calls = []

    def guarded(command, **kwargs):
        calls.append((command, kwargs))
        return 17

    operation_guard = SimpleNamespace(
        reconcile_project_operations=lambda _project_dir: [],
        run_guarded_process=guarded,
    )
    monkeypatch.setattr(manual, "_load_operation_guard", lambda: operation_guard)
    return project, lock_paths, calls, attestations


def test_self_attestation_requires_exact_installed_path(monkeypatch):
    checked = []
    monkeypatch.setattr(manual, "__file__", str(manual.SELF))
    monkeypatch.setattr(manual, "_validate_helper", checked.append)

    manual._validate_self()

    assert checked == [manual.SELF]


def test_runner_release_path_contract_matches_the_transaction_bundle():
    assert manual.BASE_RELEASE_MODES == BASE_REMOTE_ASSET_MODES
    assert scheduled.BASE_RELEASE_MODES == BASE_REMOTE_ASSET_MODES


def test_self_attestation_rejects_checkout_execution():
    with pytest.raises(RuntimeError, match="installed path"):
        manual._validate_self()


@pytest.mark.parametrize("kind", ["regular", "symlink"])
def test_any_maintenance_marker_presence_fails_closed(tmp_path, monkeypatch, kind):
    marker = tmp_path / "maintenance"
    if kind == "regular":
        marker.write_text("not-even-a-valid-marker\n")
    else:
        target = tmp_path / "target"
        target.write_text("x")
        marker.symlink_to(target)
    monkeypatch.setattr(manual, "MAINTENANCE_MARKER", marker)

    with pytest.raises(RuntimeError, match="maintenance marker is present"):
        manual._reject_maintenance_marker()


def test_scheduled_runner_rejects_any_maintenance_marker(tmp_path, monkeypatch):
    marker = tmp_path / "maintenance"
    marker.write_text("release-in-progress\n")
    monkeypatch.setattr(scheduled, "MAINTENANCE_MARKER", marker)

    with pytest.raises(RuntimeError, match="maintenance marker is present"):
        scheduled._reject_maintenance_marker()


def test_verify_uses_both_locks_and_exact_guarded_bootstrap(monkeypatch, tmp_path):
    project, lock_paths, calls, attestations = _run_setup(monkeypatch, tmp_path)

    result = manual.run_manual(
        phase="verify",
        project_dir=str(project),
        compose_file="docker-compose.patroni.yml",
        operation_id="a" * 32,
        expected_release_sha256="f" * 64,
    )

    assert result == 17
    assert lock_paths == [manual.LOCK_PATH, project / ".deploy.lock"]
    assert attestations == [
        (str(project), "docker-compose.patroni.yml", "f" * 64)
    ]
    command, kwargs = calls[0]
    assert command == ["/bin/bash", str(manual.BOOTSTRAP), "verify"]
    assert kwargs["record_command"] == str(manual.BOOTSTRAP)
    assert kwargs["operation_id"] == "a" * 32
    assert kwargs["timeout_seconds"] == 1200.0
    assert kwargs["environment"] == {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/root",
        "LANG": "C",
        "LC_ALL": "C",
        "DOCKER_CONTEXT": "default",
        "PROJECT_DIR": str(project),
        "COMPOSE_FILE": "docker-compose.patroni.yml",
        "PITR_REQUIRED": "true",
        "REQUIRE_WAL": "true",
        "BACKUP_ID": "",
        "TARGET_TIME": "",
    }


def test_logical_drill_has_installed_allowlist_and_no_runtime_overrides(
    monkeypatch, tmp_path
):
    project, _, calls, _ = _run_setup(monkeypatch, tmp_path)
    checked_state = []
    monkeypatch.setattr(manual, "_validate_state_root", checked_state.append)
    monkeypatch.setenv("POSTGRES_IMAGE", "attacker/image:latest")
    monkeypatch.setenv("KEEP_DRILL_FILES", "true")
    monkeypatch.setenv("APP_SERVICE", "attacker")

    result = manual.run_manual(
        phase="logical-restore-drill",
        project_dir=str(project),
        compose_file="docker-compose.patroni.yml",
        operation_id="b" * 32,
        expected_release_sha256="f" * 64,
        expected_database_role="standby",
    )

    assert result == 17
    assert checked_state == [manual.LOGICAL_STATE_ROOT]
    command, kwargs = calls[0]
    assert command == [str(manual.LOGICAL_DRILL)]
    assert kwargs["record_command"] == str(manual.LOGICAL_DRILL)
    assert kwargs["timeout_seconds"] == 1200.0
    environment = kwargs["environment"]
    assert environment["DRILL_ROOT"] == str(manual.LOGICAL_STATE_ROOT)
    assert environment["RESTORE_DRILL_CLEANUP_SCRIPT"] == str(manual.LOGICAL_CLEANUP)
    assert environment["EXPECTED_DATABASE_ROLE"] == "standby"
    assert "POSTGRES_IMAGE" not in environment
    assert "KEEP_DRILL_FILES" not in environment
    assert "APP_SERVICE" not in environment
    assert "BACKUP_ID" not in environment


def test_logical_drill_rejects_missing_database_role_before_lock(monkeypatch, tmp_path):
    project, lock_paths, _, _ = _run_setup(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="requires a reviewed database role"):
        manual.run_manual(
            phase="logical-restore-drill",
            project_dir=str(project),
            compose_file="docker-compose.patroni.yml",
            operation_id="b" * 32,
            expected_release_sha256="f" * 64,
        )

    assert lock_paths == []


def test_nonrestore_phases_reject_restore_selectors_before_lock(monkeypatch, tmp_path):
    project, lock_paths, _, _ = _run_setup(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="does not accept restore selectors"):
        manual.run_manual(
            phase="logical-restore-drill",
            project_dir=str(project),
            compose_file="docker-compose.patroni.yml",
            operation_id="c" * 32,
            expected_release_sha256="f" * 64,
            backup_id="unexpected",
        )

    assert lock_paths == []


def test_finalized_release_attestation_requires_exact_paths_hashes_and_digest(
    monkeypatch,
):
    project_dir = "/opt/air-api"
    compose_file = "docker-compose.patroni.yml"
    compose_path = f"{project_dir}/{compose_file}"
    monkeypatch.setattr(manual, "BASE_RELEASE_MODES", {"/usr/local/sbin/tool": 0o755})
    payloads = {
        "/usr/local/sbin/tool": b"tool\n",
        compose_path: b"services: {}\n",
    }
    release = "d" * 64
    manifest = {
        "files": [
            {
                "mode": mode,
                "path": path,
                "sha256": hashlib.sha256(payloads[path]).hexdigest(),
            }
            for path, mode in sorted(
                {"/usr/local/sbin/tool": 0o755, compose_path: 0o644}.items()
            )
        ],
        "project_dir": project_dir,
        "release_sha256": release,
        "txid": "a" * 32,
        "version": 1,
    }
    manifest_payload = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()

    def read(path, *, mode, limit):
        del mode, limit
        if path == manual.RELEASE_MANIFEST:
            return manifest_payload
        return payloads[str(path)]

    monkeypatch.setattr(manual, "_read_attested_file", read)
    assert manual._attest_finalized_release(
        project_dir,
        compose_file,
        expected_release_sha256=release,
    ) == release

    with pytest.raises(RuntimeError, match="manifest contract"):
        manual._attest_finalized_release(
            project_dir,
            compose_file,
            expected_release_sha256="e" * 64,
        )

    payloads[compose_path] = b"tampered\n"
    with pytest.raises(RuntimeError, match="hash mismatch"):
        manual._attest_finalized_release(
            project_dir,
            compose_file,
            expected_release_sha256=release,
        )
