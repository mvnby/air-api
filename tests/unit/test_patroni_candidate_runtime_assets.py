import os
import subprocess
from pathlib import Path

import pytest

from tests.unit.test_patroni_candidate_transactions import (
    PATRONI_RUNNER,
    TRANSACTION,
    _patroni_runner_env,
)


ROLE_UNIT = (
    Path(__file__).resolve().parents[2]
    / "deploy/ha/patroni/mvn-patroni-role-agent.service"
)


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _role_asset_pairs(env: dict[str, str]) -> list[tuple[Path, Path, str]]:
    return [
        (
            Path(env["PATRONI_ROLE_IDENTITY_SOURCE"]),
            Path(env["PATRONI_ROLE_IDENTITY_TARGET"]),
            "old identity\n",
        ),
        (
            Path(env["PATRONI_ROLE_AGENT_CONFIG_SOURCE"]),
            Path(env["PATRONI_ROLE_AGENT_CONFIG_TARGET"]),
            "old config\n",
        ),
        (
            Path(env["PATRONI_ROLE_COMPOSE_RUNTIME_SOURCE"]),
            Path(env["PATRONI_ROLE_COMPOSE_RUNTIME_TARGET"]),
            "old compose runtime\n",
        ),
        (
            Path(env["PATRONI_ROLE_UNIT_SOURCE"]),
            Path(env["PATRONI_ROLE_UNIT_TARGET"]),
            "[Service]\nExecStart=/old-role-agent\n",
        ),
        (
            Path(env["PATRONI_ROLE_AGENT_SOURCE"]),
            Path(env["PATRONI_ROLE_AGENT_TARGET"]),
            "#!/usr/bin/env python3\n# old role agent\n",
        ),
    ]


def _seed_previous_role_assets(env: dict[str, str]) -> None:
    for _source, target, content in _role_asset_pairs(env):
        target.write_text(content, encoding="utf-8")
        mode = 0o755 if target == Path(env["PATRONI_ROLE_AGENT_TARGET"]) else 0o644
        target.chmod(mode)


def _installed_target_order(env: dict[str, str]) -> list[str]:
    lines = Path(env["INSTALL_LOG"]).read_text(encoding="utf-8").splitlines()
    expected_targets = [str(target) for _source, target, _content in _role_asset_pairs(env)]
    assert len(lines) == len(expected_targets)
    for temporary, target in zip(lines, expected_targets, strict=True):
        assert temporary.startswith(target + ".tmp.")
    return expected_targets


def test_candidate_requires_immutable_candidate_image_before_mutation(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    env.pop("BACKEND_IMAGE")
    canonical = (project / "compose.yml").read_text(encoding="utf-8")
    candidate = (project / "compose.yml.candidate").read_text(encoding="utf-8")

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "BACKEND_IMAGE must identify an immutable candidate release" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == canonical
    assert (project / "compose.yml.candidate").read_text(encoding="utf-8") == candidate
    assert not Path(env["PATRONI_ROLE_AGENT_TARGET"]).exists()


def test_role_asset_install_orders_dependencies_and_unit_before_executable(tmp_path):
    env, _project = _patroni_runner_env(tmp_path, child_exit=0)
    _seed_previous_role_assets(env)

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert _installed_target_order(env)[-1] == env["PATRONI_ROLE_AGENT_TARGET"]
    systemctl = Path(env["SYSTEMCTL_LOG"]).read_text(encoding="utf-8").splitlines()
    assert systemctl.index("daemon-reload") < systemctl.index("restart test.service")


def test_role_asset_install_failure_restores_every_asset_in_safe_order(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    _seed_previous_role_assets(env)
    env["FAIL_INSTALL_NUMBER"] = "4"

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    install_lines = Path(env["INSTALL_LOG"]).read_text(encoding="utf-8").splitlines()
    assert len(install_lines) == 4
    assert all(
        not line.startswith(env["PATRONI_ROLE_AGENT_TARGET"] + ".tmp.")
        for line in install_lines
    )
    restore_lines = [
        line
        for line in Path(env["CP_LOG"]).read_text(encoding="utf-8").splitlines()
        if ".patroni-" in line.split("|", 1)[0]
    ]
    labels = (
        "role-identity",
        "role-agent-config",
        "compose-runtime",
        "role-agent-unit",
        "role-agent",
    )
    assert [
        next(label for label in labels if f".patroni-{label}.backup." in line)
        for line in restore_lines
    ] == list(labels)
    for _source, target, old_content in _role_asset_pairs(env):
        assert target.read_text(encoding="utf-8") == old_content
    assert not (project / "compose.yml.candidate").exists()


def test_partial_role_asset_restore_is_best_effort_and_retains_backups(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    _seed_previous_role_assets(env)
    env["FAIL_RESTORE_LABEL"] = "compose-runtime"

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 90
    assert "role asset backups retained" in result.stderr
    for _source, target, old_content in _role_asset_pairs(env):
        if target == Path(env["PATRONI_ROLE_COMPOSE_RUNTIME_TARGET"]):
            assert target.read_text(encoding="utf-8") != old_content
        else:
            assert target.read_text(encoding="utf-8") == old_content
    assert len(list(project.glob(".patroni-*.backup.*"))) == 5
    assert not (project / "compose.yml.candidate").exists()


def test_candidate_rejects_symlinked_role_agent_executable_target(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    victim = tmp_path / "victim-role-agent"
    victim.write_text("do-not-overwrite\n", encoding="utf-8")
    Path(env["PATRONI_ROLE_AGENT_TARGET"]).symlink_to(victim)

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "role agent target is unsafe" in result.stderr
    assert victim.read_text(encoding="utf-8") == "do-not-overwrite\n"
    assert not (project / "compose.yml.candidate").exists()


def test_candidate_rejects_symlinked_identity_helper_target(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    victim = tmp_path / "victim-identity-helper"
    victim.write_text("do-not-overwrite\n", encoding="utf-8")
    Path(env["PATRONI_ROLE_IDENTITY_TARGET"]).symlink_to(victim)

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "identity helper target is unsafe" in result.stderr
    assert victim.read_text(encoding="utf-8") == "do-not-overwrite\n"
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("failure_source", "child_exit", "restart_failure", "expected_exit"),
    [
        ("child", 42, "0", 42),
        ("systemctl", 0, "1", 47),
    ],
)
def test_failure_restores_preexisting_role_agent_bundle(
    tmp_path,
    failure_source,
    child_exit,
    restart_failure,
    expected_exit,
):
    env, project = _patroni_runner_env(tmp_path, child_exit=child_exit)
    target = Path(env["PATRONI_ROLE_AGENT_TARGET"])
    identity_target = Path(env["PATRONI_ROLE_IDENTITY_TARGET"])
    unit_target = Path(env["PATRONI_ROLE_UNIT_TARGET"])
    old_content = "#!/usr/bin/env python3\n# previous role agent\n"
    old_identity = "# previous identity helper\n"
    old_unit = "[Service]\nExecStart=/previous-role-agent\n"
    target.write_text(old_content, encoding="utf-8")
    target.chmod(0o755)
    identity_target.write_text(old_identity, encoding="utf-8")
    unit_target.write_text(old_unit, encoding="utf-8")
    env["SYSTEMCTL_FAIL_RESTART_NUMBER"] = restart_failure

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == expected_exit, (
        failure_source,
        result.stdout,
        result.stderr,
    )
    assert target.read_text(encoding="utf-8") == old_content
    assert identity_target.read_text(encoding="utf-8") == old_identity
    assert unit_target.read_text(encoding="utf-8") == old_unit
    assert not Path(env["PATRONI_ROLE_AGENT_SOURCE"]).exists()
    assert not Path(env["PATRONI_ROLE_IDENTITY_SOURCE"]).exists()
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    restarts = [
        line
        for line in Path(env["SYSTEMCTL_LOG"]).read_text(encoding="utf-8").splitlines()
        if line.startswith("restart ")
    ]
    assert len(restarts) == 2
    assert Path(env["RECONCILE_LOG"]).exists()


def test_restore_restart_failure_retains_role_agent_backups(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    target = Path(env["PATRONI_ROLE_AGENT_TARGET"])
    identity_target = Path(env["PATRONI_ROLE_IDENTITY_TARGET"])
    unit_target = Path(env["PATRONI_ROLE_UNIT_TARGET"])
    old_content = "#!/usr/bin/env python3\n# previous role agent\n"
    old_identity = "# previous identity helper\n"
    old_unit = "[Service]\nExecStart=/previous-role-agent\n"
    target.write_text(old_content, encoding="utf-8")
    target.chmod(0o755)
    identity_target.write_text(old_identity, encoding="utf-8")
    unit_target.write_text(old_unit, encoding="utf-8")
    env["SYSTEMCTL_FAIL_RESTART_NUMBER"] = "2"

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 90
    assert "role asset backups retained" in result.stderr
    backup_expectations = (
        (".patroni-role-agent.backup.*", old_content),
        (".patroni-role-identity.backup.*", old_identity),
        (".patroni-role-agent-unit.backup.*", old_unit),
    )
    for pattern, content in backup_expectations:
        backups = list(project.glob(pattern))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == content
    assert target.read_text(encoding="utf-8") == old_content
    assert identity_target.read_text(encoding="utf-8") == old_identity
    assert unit_target.read_text(encoding="utf-8") == old_unit
    assert not (project / "compose.yml.candidate").exists()


def test_first_rollout_role_drift_force_removes_candidate_worker_after_stop_failure(
    tmp_path,
):
    env, project = _patroni_runner_env(
        tmp_path,
        child_exit=42,
        expected_role="primary",
        current_role="standby",
    )
    Path(env["WORKER_RUNTIME_STATE"]).touch()
    env["FAKE_CANDIDATE_WORKER_SUPPORTED"] = "true"
    env["FAKE_CANONICAL_WORKER_SUPPORTED"] = "false"
    env["FAIL_CANDIDATE_WORKER_STOP"] = "true"

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 90
    assert "Patroni role changed during deployment" in result.stderr
    assert not Path(env["WORKER_RUNTIME_STATE"]).exists()
    assert not (project / "compose.yml.candidate").exists()
    assert (project / ".ha-communications-worker-release-fenced").exists()
    commands = Path(env["PATRONI_COMMAND_LOG"]).read_text(encoding="utf-8")
    assert " stop communications-worker" in commands
    assert "ps -a -q --filter label=com.docker.compose.project=air-api" in commands
    assert "rm -f -- " + "0" * 64 in commands


def test_preexisting_release_fence_rolls_back_to_stopped_worker(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    marker = project / ".ha-communications-worker-release-fenced"
    marker.write_text("fenced\n", encoding="utf-8")
    marker.chmod(0o600)
    env.update(
        {
            "BACKEND_IMAGE": "ghcr.io/mvnby/air-api/backend@" + "sha256:" + "2" * 64,
            "FAKE_CANONICAL_WORKER_SUPPORTED": "true",
            "FAKE_CANDIDATE_WORKER_SUPPORTED": "true",
        }
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 42, result.stderr
    assert marker.read_text(encoding="utf-8") == "fenced\n"
    assert marker.stat().st_mode & 0o777 == 0o600
    assert not Path(env["WORKER_RUNTIME_STATE"]).exists()
    assert Path(env["RECONCILE_LOG"]).read_text(encoding="utf-8").strip() == (
        "compose.yml|app"
    )


def test_first_rollout_preexisting_fence_proves_no_labeled_worker(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    marker = project / ".ha-communications-worker-release-fenced"
    marker.write_text("fenced\n", encoding="utf-8")
    marker.chmod(0o600)
    env.update(
        {
            "FAKE_CANONICAL_WORKER_SUPPORTED": "false",
            "FAKE_CANDIDATE_WORKER_SUPPORTED": "true",
        }
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 42, result.stderr
    assert marker.read_text(encoding="utf-8") == "fenced\n"
    assert not Path(env["WORKER_RUNTIME_STATE"]).exists()
    commands = Path(env["PATRONI_COMMAND_LOG"]).read_text(encoding="utf-8")
    canonical_unknown_service_probe = (
        f"compose -f {project / 'compose.yml'} --profile bluegreen "
        "ps --status running -q communications-worker"
    )
    assert canonical_unknown_service_probe not in commands
    assert (
        "ps -a -q --filter label=com.docker.compose.project=air-api "
        "--filter label=com.docker.compose.service=communications-worker"
    ) in commands
    assert Path(env["RECONCILE_LOG"]).read_text(encoding="utf-8").strip() == (
        "compose.yml|app"
    )


def test_unfenced_running_worker_is_restored_after_candidate_failure(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    worker_state = Path(env["WORKER_RUNTIME_STATE"])
    worker_state.touch()
    env.update(
        {
            "BACKEND_IMAGE": "ghcr.io/mvnby/air-api/backend@" + "sha256:" + "2" * 64,
            "FAKE_CANONICAL_WORKER_SUPPORTED": "true",
            "FAKE_CANDIDATE_WORKER_SUPPORTED": "true",
        }
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 42, result.stderr
    assert worker_state.exists()
    assert not (project / ".ha-communications-worker-release-fenced").exists()
    assert Path(env["RECONCILE_LOG"]).read_text(encoding="utf-8").strip() == (
        "compose.yml|app communications-worker"
    )


def test_broken_symlink_release_fence_is_preserved_and_rejected(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    marker = project / ".ha-communications-worker-release-fenced"
    missing_target = tmp_path / "missing-marker-target"
    marker.symlink_to(missing_target)
    env.update(
        {
            "BACKEND_IMAGE": "ghcr.io/mvnby/air-api/backend@" + "sha256:" + "2" * 64,
            "FAKE_CANONICAL_WORKER_SUPPORTED": "true",
            "FAKE_CANDIDATE_WORKER_SUPPORTED": "true",
        }
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "communications worker release fence metadata is unsafe" in result.stderr
    assert marker.is_symlink()
    assert not missing_target.exists()
    assert not Path(env["PATRONI_ROLE_AGENT_TARGET"]).exists()
    assert not (project / "compose.yml.candidate").exists()


def test_post_promotion_failure_latches_durable_worker_fence(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    transaction_driver = tmp_path / "promotion-failure.sh"
    _executable(
        transaction_driver,
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "promote" ]]; then
  bash "$REAL_TRANSACTION" "$1"
  exit 46
fi
exec bash "$REAL_TRANSACTION" "$@"
""",
    )
    env.update(
        {
            "COMPOSE_CANDIDATE_TRANSACTION_SCRIPT": str(transaction_driver),
            "REAL_TRANSACTION": str(TRANSACTION),
            "FAKE_CANDIDATE_WORKER_SUPPORTED": "true",
        }
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 46, result.stderr
    assert not (project / "compose.yml.candidate").exists()
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
    marker = project / ".ha-communications-worker-release-fenced"
    assert marker.read_text(encoding="utf-8") == "fenced\n"
    assert marker.stat().st_mode & 0o777 == 0o600


def test_role_agent_unit_requires_complete_modular_runtime():
    unit = ROLE_UNIT.read_text(encoding="utf-8")

    for path in (
        "/usr/local/sbin/mvn-patroni-role-agent",
        "/usr/local/sbin/patroni_local_identity.py",
        "/usr/local/sbin/patroni_role_agent_config.py",
        "/usr/local/sbin/patroni_compose_runtime.py",
    ):
        assert f"ConditionPathExists={path}" in unit
