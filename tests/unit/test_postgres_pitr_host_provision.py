import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from scripts.ha import provision_postgres_pitr_host as provision


class SystemdRunner:
    def __init__(
        self,
        *,
        active_state: str = "inactive",
        identity_uid: int | None = None,
        identity_gid: int | None = None,
        fail_first_action: bool = False,
        security_options: list[str] | None = None,
        role_agent_state: str = "inactive",
    ):
        self.active_state = active_state
        self.identity_uid = os.geteuid() if identity_uid is None else identity_uid
        self.identity_gid = os.getegid() if identity_gid is None else identity_gid
        self.fail_first_action = fail_first_action
        self.security_options = security_options or ["name=seccomp,profile=builtin"]
        self.role_agent_state = role_agent_state
        self.failed_action = False
        self.calls = []

    def __call__(self, args):
        values = list(args)
        self.calls.append(values)
        if values[:2] == ["docker", "compose"] and values[-3:] == ["ps", "-q", "db"]:
            return subprocess.CompletedProcess(values, 0, "a" * 64 + "\n", "")
        if values[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(
                values,
                0,
                f"sha256:{'b' * 64}|ghcr.io/mvn/patroni@sha256:{'c' * 64}||\n",
                "",
            )
        if values[:2] == ["docker", "info"]:
            return subprocess.CompletedProcess(
                values,
                0,
                json.dumps(self.security_options) + "\n",
                "",
            )
        if values[:2] == ["docker", "exec"]:
            identity = f"{self.identity_uid}:{self.identity_gid}"
            return subprocess.CompletedProcess(values, 0, f"{identity}|{identity}\n", "")
        if values[:1] != ["systemctl"]:
            return subprocess.CompletedProcess(values, 70, "", "unexpected command")
        if values[1:2] == ["is-enabled"]:
            return subprocess.CompletedProcess(values, 1, "disabled\n", "")
        if values[1:2] == ["is-active"]:
            state = (
                self.role_agent_state
                if values[-1] == provision.ROLE_AGENT_UNIT
                else self.active_state
            )
            code = 3 if state == "inactive" else 0
            return subprocess.CompletedProcess(values, code, state + "\n", "")
        if self.fail_first_action and not self.failed_action:
            self.failed_action = True
            return subprocess.CompletedProcess(values, 1, "", "simulated partial failure")
        return subprocess.CompletedProcess(values, 0, "", "")


def _fixture_paths(tmp_path: Path, transaction_id: str):
    project = tmp_path / "project"
    project.mkdir()
    compose = project / "docker-compose.patroni.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    run_root = tmp_path / "run"
    etc_root = tmp_path / "etc"
    run_root.mkdir()
    etc_root.mkdir()
    marker = run_root / "mvn-postgres-pitr-maintenance"
    marker.write_text(transaction_id + "\n", encoding="ascii")
    marker.chmod(0o600)
    paths = provision.ProvisionPaths(
        state_root=tmp_path / "state",
        record_root=run_root / "operations",
        systemd_env=etc_root / "mvn-postgres-pitr.env",
        maintenance_marker=marker,
    )
    targets = {str(project): (compose.name, "test-node")}
    return project, compose, paths, targets


def _provision(tmp_path: Path, *, transaction_id: str = "a" * 32, runner=None):
    project, compose, paths, targets = _fixture_paths(tmp_path, transaction_id)
    uid = os.geteuid()
    gid = os.getegid()
    selected_runner = runner or SystemdRunner()
    receipt = provision.provision_host(
        project_dir=str(project),
        compose_file=compose.name,
        transaction_id=transaction_id,
        paths=paths,
        runner=selected_runner,
        expected_uid=uid,
        expected_gid=gid,
        archive_uid=uid,
        archive_gid=gid,
        allowed_targets=targets,
    )
    return project, compose, paths, targets, selected_runner, receipt


def test_provision_creates_exact_state_env_and_idempotent_receipt(tmp_path):
    transaction_id = "b" * 32
    project, compose, paths, targets = _fixture_paths(tmp_path, transaction_id)
    archive = project / "postgres-wal-archive"
    archive.mkdir(mode=0o755)
    wal = archive / "000000010000000000000001"
    with wal.open("wb") as stream:
        stream.truncate(provision.WAL_SEGMENT_BYTES)
    wal.chmod(0o644)
    uid = os.geteuid()
    gid = os.getegid()
    runner = SystemdRunner()

    first = provision.provision_host(
        project_dir=str(project),
        compose_file=compose.name,
        transaction_id=transaction_id,
        paths=paths,
        runner=runner,
        expected_uid=uid,
        expected_gid=gid,
        archive_uid=uid,
        archive_gid=gid,
        allowed_targets=targets,
    )
    second = provision.provision_host(
        project_dir=str(project),
        compose_file=compose.name,
        transaction_id=transaction_id,
        paths=paths,
        runner=runner,
        expected_uid=uid,
        expected_gid=gid,
        archive_uid=uid,
        archive_gid=gid,
        allowed_targets=targets,
    )

    assert first == second
    assert first.is_file()
    assert stat.S_IMODE(first.stat().st_mode) == 0o600
    assert paths.systemd_env.read_text(encoding="ascii") == (
        f"PROJECT_DIR={project}\nCOMPOSE_FILE={compose.name}\n"
    )
    assert stat.S_IMODE(paths.systemd_env.stat().st_mode) == 0o600
    assert stat.S_IMODE(archive.stat().st_mode) == 0o700
    assert stat.S_IMODE(wal.stat().st_mode) == 0o600
    archive_lock = archive / provision.ARCHIVE_LOCK_NAME
    assert archive_lock.is_file()
    assert stat.S_IMODE(archive_lock.stat().st_mode) == 0o600
    for name in (
        "basebackups",
        "restore-drills",
        "logical-restore-drills",
        "transactions",
        "transactions-receipts",
        "provision-receipts",
    ):
        assert stat.S_IMODE((paths.state_root / name).stat().st_mode) == 0o700
    for timer in provision.TIMER_UNITS:
        assert runner.calls.count(["systemctl", "disable", "--now", timer]) == 4


def test_provision_rejects_wrong_or_unsafe_maintenance_marker(tmp_path):
    transaction_id = "c" * 32
    project, compose, paths, targets = _fixture_paths(tmp_path, transaction_id)
    paths.maintenance_marker.write_text("d" * 32 + "\n", encoding="ascii")
    paths.maintenance_marker.chmod(0o600)

    with pytest.raises(RuntimeError, match="another transaction"):
        provision.provision_host(
            project_dir=str(project),
            compose_file=compose.name,
            transaction_id=transaction_id,
            paths=paths,
            runner=SystemdRunner(),
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            archive_uid=os.geteuid(),
            archive_gid=os.getegid(),
            allowed_targets=targets,
        )

    paths.maintenance_marker.unlink()
    target = paths.maintenance_marker.with_suffix(".target")
    target.write_text(transaction_id + "\n", encoding="ascii")
    target.chmod(0o600)
    paths.maintenance_marker.symlink_to(target)
    with pytest.raises(RuntimeError, match="unsafe PITR control file"):
        provision.provision_host(
            project_dir=str(project),
            compose_file=compose.name,
            transaction_id=transaction_id,
            paths=paths,
            runner=SystemdRunner(),
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            archive_uid=os.geteuid(),
            archive_gid=os.getegid(),
            allowed_targets=targets,
        )


def test_provision_rejects_unknown_archive_entry_before_quiescing(tmp_path):
    transaction_id = "e" * 32
    project, compose, paths, targets = _fixture_paths(tmp_path, transaction_id)
    archive = project / "postgres-wal-archive"
    archive.mkdir()
    (archive / "attacker-file").write_text("x", encoding="utf-8")
    runner = SystemdRunner()

    with pytest.raises(RuntimeError, match="unexpected entry"):
        provision.provision_host(
            project_dir=str(project),
            compose_file=compose.name,
            transaction_id=transaction_id,
            paths=paths,
            runner=runner,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            archive_uid=os.geteuid(),
            archive_gid=os.getegid(),
            allowed_targets=targets,
        )

    assert ["systemctl", "is-active", provision.ROLE_AGENT_UNIT] in runner.calls
    assert not any(
        call[:2] in {
            ("systemctl", "disable"),
            ("systemctl", "stop"),
            ("systemctl", "reset-failed"),
            ("systemctl", "daemon-reload"),
        }
        for call in map(tuple, runner.calls)
    )


@pytest.mark.parametrize(
    ("size", "accepted"),
    [
        (provision.WAL_SEGMENT_BYTES, True),
        (provision.WAL_SEGMENT_BYTES - 1, False),
        (provision.WAL_SEGMENT_BYTES + 1, False),
    ],
)
def test_provision_validates_promotion_partial_as_exact_wal_segment(
    tmp_path, size, accepted
):
    archive = tmp_path / "archive"
    archive.mkdir(mode=0o700)
    partial = archive / "00000007000000000000004B.partial"
    with partial.open("wb") as stream:
        stream.truncate(size)
    partial.chmod(0o600)

    if accepted:
        provision._provision_archive(
            archive,
            archive_uid=os.geteuid(),
            archive_gid=os.getegid(),
        )
        assert partial.stat().st_size == provision.WAL_SEGMENT_BYTES
    else:
        with pytest.raises(RuntimeError, match="invalid PITR WAL segment size"):
            provision._provision_archive(
                archive,
                archive_uid=os.geteuid(),
                archive_gid=os.getegid(),
            )


@pytest.mark.parametrize("state", ["active", "activating", "failed", "unknown"])
def test_role_agent_must_be_exactly_inactive_before_host_state_mutation(
    tmp_path, state
):
    transaction_id = "9" * 32
    project, compose, paths, targets = _fixture_paths(tmp_path, transaction_id)
    runner = SystemdRunner(role_agent_state=state)

    with pytest.raises(RuntimeError, match="role agent must be exactly inactive"):
        provision.provision_host(
            project_dir=str(project),
            compose_file=compose.name,
            transaction_id=transaction_id,
            paths=paths,
            runner=runner,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            archive_uid=os.geteuid(),
            archive_gid=os.getegid(),
            allowed_targets=targets,
        )

    assert not paths.state_root.exists()
    assert not paths.record_root.exists()
    assert not paths.systemd_env.exists()
    assert not (project / "postgres-wal-archive").exists()


def test_provision_fails_if_units_do_not_quiesce(tmp_path):
    runner = SystemdRunner(active_state="active")
    with pytest.raises(RuntimeError, match="did not converge"):
        _provision(tmp_path, runner=runner)


def test_provision_attempts_full_quiescence_after_partial_systemd_failure(tmp_path):
    runner = SystemdRunner(fail_first_action=True)

    with pytest.raises(RuntimeError, match="safe postconditions after command failures"):
        _provision(tmp_path, runner=runner)

    for timer in provision.TIMER_UNITS:
        assert runner.calls.count(["systemctl", "disable", "--now", timer]) == 2
        assert ["systemctl", "is-enabled", timer] in runner.calls
    for service in provision.SERVICE_UNITS:
        assert runner.calls.count(["systemctl", "stop", service]) == 2
    for unit in provision.SYSTEMD_UNITS:
        assert ["systemctl", "is-active", unit] in runner.calls


def test_postgres_identity_mismatch_precedes_every_host_state_mutation(tmp_path):
    transaction_id = "f" * 32
    project, compose, paths, targets = _fixture_paths(tmp_path, transaction_id)
    runner = SystemdRunner(identity_uid=os.geteuid() + 1)

    with pytest.raises(RuntimeError, match="UID/GID"):
        provision.provision_host(
            project_dir=str(project),
            compose_file=compose.name,
            transaction_id=transaction_id,
            paths=paths,
            runner=runner,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            archive_uid=os.geteuid(),
            archive_gid=os.getegid(),
            allowed_targets=targets,
        )

    assert not paths.state_root.exists()
    assert not paths.record_root.exists()
    assert not paths.systemd_env.exists()
    assert not (project / "postgres-wal-archive").exists()


def test_rootless_docker_is_rejected_before_host_state_mutation(tmp_path):
    transaction_id = "1" * 32
    project, compose, paths, targets = _fixture_paths(tmp_path, transaction_id)
    runner = SystemdRunner(
        security_options=["name=seccomp,profile=builtin", "name=rootless"]
    )

    with pytest.raises(RuntimeError, match="rootless"):
        provision.provision_host(
            project_dir=str(project),
            compose_file=compose.name,
            transaction_id=transaction_id,
            paths=paths,
            runner=runner,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            archive_uid=os.geteuid(),
            archive_gid=os.getegid(),
            allowed_targets=targets,
        )

    assert not paths.state_root.exists()
    assert not (project / "postgres-wal-archive").exists()


def test_provision_rejects_tampered_completion_receipt(tmp_path):
    project, compose, paths, targets, runner, receipt = _provision(tmp_path)
    receipt.write_text("{}\n", encoding="ascii")
    receipt.chmod(0o600)

    with pytest.raises(RuntimeError, match="receipt conflicts"):
        provision.provision_host(
            project_dir=str(project),
            compose_file=compose.name,
            transaction_id="a" * 32,
            paths=paths,
            runner=runner,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            archive_uid=os.geteuid(),
            archive_gid=os.getegid(),
            allowed_targets=targets,
        )
