import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSACTION = REPO_ROOT / "scripts/compose_candidate_transaction.sh"
PATRONI_RUNNER = REPO_ROOT / "scripts/ha/run_patroni_candidate_transaction.sh"
PREVIOUS_IMAGE = "ghcr.io/mvnby/air-api/backend:" + "1" * 40


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _compose_pair(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "compose.yml").write_text(
        "services:\n  app:\n    volumes:\n      - ./token.json:/app/token.json\n",
        encoding="utf-8",
    )
    (project / "compose.yml.candidate").write_text(
        "services:\n  app:\n    volumes:\n      - ./google-oauth:/app/google-oauth\n",
        encoding="utf-8",
    )
    return project


def _patroni_runner_env(
    tmp_path: Path,
    child_exit: int,
    *,
    current_role: str = "primary",
    expected_role: str = "primary",
    discover_previous: bool = False,
) -> tuple[dict[str, str], Path]:
    project = _compose_pair(tmp_path)
    if discover_previous:
        (project / ".active-api-slot").write_text("green\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    command_log = tmp_path / "patroni-commands.log"
    command_log.touch()
    systemctl_log = tmp_path / "systemctl.log"
    systemctl_log.touch()
    systemctl_state = tmp_path / "systemctl-state"
    systemctl_state.write_text("active\n", encoding="utf-8")
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$PATRONI_COMMAND_LOG"
if [[ "$1" == "compose" && "$*" == *" ps -q app-green" ]]; then
  printf 'active-green-container\n'
elif [[ "$1" == "inspect" && "$*" == *" active-green-container" ]]; then
  printf '%s\n' "$EXPECTED_PREVIOUS_IMAGE"
elif [[ "$1" == "compose" && "$*" == *" stop app app-blue app-green bot" ]]; then
  exit 0
else
  exit 91
fi
""",
    )
    _executable(
        fake_bin / "systemctl",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$SYSTEMCTL_LOG"
case "$1" in
  restart)
    count=0
    if [[ -f "$SYSTEMCTL_RESTART_COUNT" ]]; then
      count="$(cat "$SYSTEMCTL_RESTART_COUNT")"
    fi
    count=$((count + 1))
    printf '%s\n' "$count" > "$SYSTEMCTL_RESTART_COUNT"
    if [[ "$count" -eq "${SYSTEMCTL_FAIL_RESTART_NUMBER:-0}" ]]; then
      printf 'inactive\n' > "$SYSTEMCTL_STATE"
      exit 47
    fi
    printf 'active\n' > "$SYSTEMCTL_STATE"
    ;;
  start)
    printf 'active\n' > "$SYSTEMCTL_STATE"
    ;;
  stop)
    printf 'inactive\n' > "$SYSTEMCTL_STATE"
    ;;
  is-active)
    [[ "$(cat "$SYSTEMCTL_STATE")" == "active" ]]
    ;;
esac
""",
    )
    child = tmp_path / "deploy-child.sh"
    _executable(
        child,
        f'''#!/usr/bin/env bash
set -euo pipefail
grep -Fq '/app/token.json' "$API_PROJECT_DIR/compose.yml"
printf "%s|%s\n" "$API_COMPOSE_FILE" "$API_DEPLOY_LOCK_ALREADY_HELD" > "$CHILD_LOG"
exit {child_exit}
''',
    )
    role_agent = tmp_path / "role-agent.py"
    role_agent.write_text("#!/usr/bin/env python3\n# new role agent\n", encoding="utf-8")
    role_identity = tmp_path / "patroni-local-identity.py"
    role_identity.write_text("# new identity helper\n", encoding="utf-8")
    reconcile = tmp_path / "reconcile.sh"
    _executable(
        reconcile,
        """#!/usr/bin/env bash
set -euo pipefail
grep -Fq '/app/token.json' "$API_PROJECT_DIR/$API_COMPOSE_FILE"
printf '%s|%s\n' "$API_COMPOSE_FILE" "$API_DEPLOY_SERVICES" > "$RECONCILE_LOG"
printf 'reconcile:%s\n' "$API_COMPOSE_FILE" >> "$PATRONI_COMMAND_LOG"
test "$API_RECONCILE_BACKEND_IMAGE" = "$EXPECTED_PREVIOUS_IMAGE"
exit 0
""",
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "PATRONI_CANDIDATE_OPERATION": "deploy",
        "API_PROJECT_DIR": str(project),
        "PATRONI_CANONICAL_COMPOSE_FILE": str(project / "compose.yml"),
        "PATRONI_CANDIDATE_COMPOSE_FILE": str(project / "compose.yml.candidate"),
        "COMPOSE_CANDIDATE_TRANSACTION_SCRIPT": str(TRANSACTION),
        "PATRONI_DEPLOY_SCRIPT": str(child),
        "API_RECONCILE_SCRIPT": str(reconcile),
        "API_EXPECTED_PATRONI_ROLE": expected_role,
        "API_CURRENT_PATRONI_ROLE": current_role,
        "PATRONI_ROLE_AGENT_SOURCE": str(role_agent),
        "PATRONI_ROLE_AGENT_TARGET": str(tmp_path / "installed-role-agent"),
        "PATRONI_ROLE_IDENTITY_SOURCE": str(role_identity),
        "PATRONI_ROLE_IDENTITY_TARGET": str(tmp_path / "installed-role-identity.py"),
        "PATRONI_ROLE_AGENT_UNIT": "test.service",
        "CHILD_LOG": str(tmp_path / "child.log"),
        "RECONCILE_LOG": str(tmp_path / "reconcile.log"),
        "PATRONI_COMMAND_LOG": str(command_log),
        "SYSTEMCTL_LOG": str(systemctl_log),
        "SYSTEMCTL_STATE": str(systemctl_state),
        "SYSTEMCTL_RESTART_COUNT": str(tmp_path / "systemctl-restart-count"),
        "API_PREVIOUS_BACKEND_IMAGE": "" if discover_previous else PREVIOUS_IMAGE,
        "EXPECTED_PREVIOUS_IMAGE": PREVIOUS_IMAGE,
    }
    return env, project


def test_patroni_candidate_failure_leaves_canonical_old(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    old = (project / "compose.yml").read_text(encoding="utf-8")

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 42
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()
    assert (tmp_path / "child.log").read_text(encoding="utf-8").strip() == "compose.yml.candidate|true"
    assert (tmp_path / "reconcile.log").read_text(encoding="utf-8").strip() == "compose.yml|app bot"


def test_patroni_candidate_promotes_only_after_success(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    new = (project / "compose.yml.candidate").read_text(encoding="utf-8")

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == new
    assert not (project / "compose.yml.candidate").exists()
    assert not (tmp_path / "reconcile.log").exists()
    assert Path(env["PATRONI_ROLE_IDENTITY_TARGET"]).read_text() == (
        "# new identity helper\n"
    )


def test_patroni_candidate_rejects_symlinked_identity_helper_target(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    victim = tmp_path / "victim"
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


def test_patroni_discovers_previous_runtime_image_from_active_slot_before_reconcile(
    tmp_path,
):
    env, project = _patroni_runner_env(
        tmp_path,
        child_exit=42,
        discover_previous=True,
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 42, result.stderr
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    commands = (tmp_path / "patroni-commands.log").read_text(encoding="utf-8").splitlines()
    ps_index = next(i for i, line in enumerate(commands) if " ps -q app-green" in line)
    inspect_index = next(
        i for i, line in enumerate(commands) if line.startswith("inspect --format ")
    )
    reconcile_index = commands.index("reconcile:compose.yml")
    assert ps_index < inspect_index < reconcile_index
    assert (tmp_path / "reconcile.log").read_text(encoding="utf-8").strip() == (
        "compose.yml|app bot"
    )


def test_patroni_role_drift_fences_all_api_slots_and_bot_without_reconcile(tmp_path):
    env, project = _patroni_runner_env(
        tmp_path,
        child_exit=42,
        expected_role="primary",
        current_role="standby",
    )
    old = (project / "compose.yml").read_text(encoding="utf-8")

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 90
    assert "Patroni role changed during deployment" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()
    assert not (tmp_path / "reconcile.log").exists()
    commands = (tmp_path / "patroni-commands.log").read_text(encoding="utf-8").splitlines()
    assert any(
        " stop app app-blue app-green bot" in command for command in commands
    )


def test_patroni_unknown_live_role_fences_runtime_instead_of_assuming_standby(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    env.pop("API_CURRENT_PATRONI_ROLE")
    _executable(
        tmp_path / "bin/curl",
        "#!/usr/bin/env bash\nprintf '%s\n' '{\"state\":\"running\",\"role\":\"mystery\"}'\n",
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 90
    assert "could not establish live Patroni role" in result.stderr
    assert not (project / "compose.yml.candidate").exists()
    assert not (tmp_path / "reconcile.log").exists()
    commands = (tmp_path / "patroni-commands.log").read_text(encoding="utf-8")
    assert " stop app app-blue app-green bot" in commands


@pytest.mark.parametrize(
    ("failure_source", "child_exit", "restart_failure", "expected_exit"),
    [
        ("child", 42, "0", 42),
        ("systemctl", 0, "1", 47),
    ],
)
def test_patroni_failure_restores_preexisting_role_agent(
    tmp_path,
    failure_source,
    child_exit,
    restart_failure,
    expected_exit,
):
    env, project = _patroni_runner_env(tmp_path, child_exit=child_exit)
    target = Path(env["PATRONI_ROLE_AGENT_TARGET"])
    identity_target = Path(env["PATRONI_ROLE_IDENTITY_TARGET"])
    old_content = "#!/usr/bin/env python3\n# previous role agent\n"
    old_identity = "# previous identity helper\n"
    target.write_text(old_content, encoding="utf-8")
    target.chmod(0o755)
    identity_target.write_text(old_identity, encoding="utf-8")
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
    assert not Path(env["PATRONI_ROLE_AGENT_SOURCE"]).exists()
    assert not Path(env["PATRONI_ROLE_IDENTITY_SOURCE"]).exists()
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    restarts = [
        line
        for line in (tmp_path / "systemctl.log").read_text(encoding="utf-8").splitlines()
        if line.startswith("restart ")
    ]
    assert len(restarts) == 2
    assert (tmp_path / "reconcile.log").exists()


def test_patroni_retains_role_agent_backup_when_restore_restart_fails(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    target = Path(env["PATRONI_ROLE_AGENT_TARGET"])
    identity_target = Path(env["PATRONI_ROLE_IDENTITY_TARGET"])
    old_content = "#!/usr/bin/env python3\n# previous role agent\n"
    old_identity = "# previous identity helper\n"
    target.write_text(old_content, encoding="utf-8")
    target.chmod(0o755)
    identity_target.write_text(old_identity, encoding="utf-8")
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
    backups = list(project.glob(".patroni-role-agent.backup.*"))
    identity_backups = list(project.glob(".patroni-role-identity.backup.*"))
    assert len(backups) == 1
    assert len(identity_backups) == 1
    assert backups[0].read_text(encoding="utf-8") == old_content
    assert identity_backups[0].read_text(encoding="utf-8") == old_identity
    assert target.read_text(encoding="utf-8") == old_content
    assert identity_target.read_text(encoding="utf-8") == old_identity
    assert not (project / "compose.yml.candidate").exists()


@pytest.mark.parametrize("migration_exit", [0, 48])
def test_patroni_migration_always_cleans_candidate_without_promoting(
    tmp_path,
    migration_exit,
):
    project = _compose_pair(tmp_path)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    migration_log = tmp_path / "migration.log"
    migration = tmp_path / "migration.sh"
    _executable(
        migration,
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$API_COMPOSE_FILE" > "$MIGRATION_LOG"
exit {migration_exit}
""",
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env={
            **os.environ,
            "PATRONI_CANDIDATE_OPERATION": "migrate",
            "API_PROJECT_DIR": str(project),
            "PATRONI_CANONICAL_COMPOSE_FILE": str(project / "compose.yml"),
            "PATRONI_CANDIDATE_COMPOSE_FILE": str(project / "compose.yml.candidate"),
            "COMPOSE_CANDIDATE_TRANSACTION_SCRIPT": str(TRANSACTION),
            "PATRONI_MIGRATION_SCRIPT": str(migration),
            "MIGRATION_LOG": str(migration_log),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == migration_exit, result.stderr
    assert migration_log.read_text(encoding="utf-8").strip() == "compose.yml.candidate"
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()


def test_patroni_post_rename_promotion_error_preserves_new_canonical(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    new = (project / "compose.yml.candidate").read_text(encoding="utf-8")
    transaction_driver = tmp_path / "patroni-transaction.sh"
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
        }
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 46
    assert "promotion committed" in result.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == new
    assert not (project / "compose.yml.candidate").exists()
    assert not (tmp_path / "reconcile.log").exists()


def test_legacy_source_bind_deploy_is_retired():
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "deploy_api.sh")],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "retired" in result.stderr
    assert "GitHub Actions image workflow" in result.stderr
