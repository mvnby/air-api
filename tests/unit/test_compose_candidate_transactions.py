import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSACTION = REPO_ROOT / "scripts/compose_candidate_transaction.sh"
BACKEND_RUNNER = REPO_ROOT / "scripts/deploy_backend_candidate_transaction.sh"
PATRONI_RUNNER = REPO_ROOT / "scripts/ha/run_patroni_candidate_transaction.sh"
PREVIOUS_IMAGE = "ghcr.io/mvnby/air-api/backend:" + "1" * 40


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _transaction(project: Path, action: str):
    return subprocess.run(
        ["bash", str(TRANSACTION), action],
        env={
            **os.environ,
            "CANONICAL_COMPOSE_FILE": str(project / "compose.yml"),
            "CANDIDATE_COMPOSE_FILE": str(project / "compose.yml.candidate"),
        },
        text=True,
        capture_output=True,
        check=False,
    )


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


def test_candidate_transaction_keeps_canonical_until_atomic_promotion(tmp_path):
    project = _compose_pair(tmp_path)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    new = (project / "compose.yml.candidate").read_text(encoding="utf-8")

    staged = _transaction(project, "stage")
    assert staged.returncode == 0, staged.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert (project / "compose.yml.candidate").read_text(encoding="utf-8") == new
    assert not (project / "compose.yml.rollback-candidate").exists()
    assert (project / "compose.yml.pre-google-oauth-dir").read_text(encoding="utf-8") == old

    promoted = _transaction(project, "promote")
    assert promoted.returncode == 0, promoted.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == new
    assert not (project / "compose.yml.candidate").exists()

    script = TRANSACTION.read_text(encoding="utf-8")
    assert 'fsync_path "${CANDIDATE_FILE}"' in script
    assert 'fsync_path "$(dirname "${CANONICAL_FILE}")"' in script


def test_candidate_cleanup_only_removes_this_runs_candidate(tmp_path):
    project = _compose_pair(tmp_path)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    assert _transaction(project, "stage").returncode == 0

    cleaned = _transaction(project, "cleanup")

    assert cleaned.returncode == 0, cleaned.stderr
    assert (project / "compose.yml").read_text(encoding="utf-8") == old
    assert not (project / "compose.yml.candidate").exists()
    assert not (project / "compose.yml.rollback-candidate").exists()


def _backend_runner(
    tmp_path: Path,
    *,
    strategy: str = "in_place",
    child_exit: int = 0,
    smoke_exit: int = 0,
    promote_exit: int = 0,
    promote_after_move_exit: int = 0,
    reconcile_exit: int = 0,
    discover_previous: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    project = _compose_pair(tmp_path)
    if discover_previous:
        (project / ".active-api-slot").write_text("green\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(
        fake_bin / "flock",
        "#!/usr/bin/env bash\nprintf 'flock:%s\\n' \"$*\" >> \"$ORDER_LOG\"\nexit 0\n",
    )
    order_log = tmp_path / "order.log"
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'docker:%s\n' "$*" >> "$ORDER_LOG"
if [[ "$1" == "compose" && "$*" == *" ps -q app-green" ]]; then
  printf 'active-green-container\n'
elif [[ "$1" == "inspect" && "$*" == *" active-green-container" ]]; then
  printf '%s\n' "$EXPECTED_PREVIOUS_IMAGE"
else
  exit 91
fi
""",
    )
    child = tmp_path / "deploy-child.sh"
    _executable(
        child,
        f"""#!/usr/bin/env bash
set -euo pipefail
grep -Fq '/app/token.json' "$API_PROJECT_DIR/compose.yml"
grep -Fq '/app/google-oauth' "$API_PROJECT_DIR/$API_COMPOSE_FILE"
printf 'child:%s:lock=%s\n' "$API_COMPOSE_FILE" "$API_DEPLOY_LOCK_ALREADY_HELD" >> "$ORDER_LOG"
exit {child_exit}
""",
    )
    smoke = tmp_path / "smoke.sh"
    _executable(
        smoke,
        f"""#!/usr/bin/env bash
set -euo pipefail
grep -Fq '/app/token.json' "$API_PROJECT_DIR/compose.yml"
grep -Fq '/app/google-oauth' "$COMPOSE_FILE"
printf 'smoke:%s\n' "$COMPOSE_FILE" >> "$ORDER_LOG"
exit {smoke_exit}
""",
    )
    reconcile = tmp_path / "reconcile.sh"
    _executable(
        reconcile,
        f"""#!/usr/bin/env bash
set -euo pipefail
grep -Fq '/app/token.json' "$API_PROJECT_DIR/$API_COMPOSE_FILE"
printf 'reconcile:%s\n' "$API_COMPOSE_FILE" >> "$ORDER_LOG"
test "$API_RECONCILE_BACKEND_IMAGE" = "$EXPECTED_PREVIOUS_IMAGE"
exit {reconcile_exit}
""",
    )
    transaction_driver = tmp_path / "transaction.sh"
    _executable(
        transaction_driver,
        f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "promote" && {promote_exit} -ne 0 ]]; then exit {promote_exit}; fi
if [[ "$1" == "promote" && {promote_after_move_exit} -ne 0 ]]; then
  bash "$REAL_TRANSACTION" "$1"
  exit {promote_after_move_exit}
fi
exec bash "$REAL_TRANSACTION" "$@"
""",
    )
    result = subprocess.run(
        ["bash", str(BACKEND_RUNNER)],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "ORDER_LOG": str(order_log),
            "API_PROJECT_DIR": str(project),
            "API_CANONICAL_COMPOSE_FILE": str(project / "compose.yml"),
            "API_CANDIDATE_COMPOSE_FILE": str(project / "compose.yml.candidate"),
            "API_DEPLOY_STRATEGY": strategy,
            "API_IN_PLACE_DEPLOY_SCRIPT": str(child),
            "API_BLUE_GREEN_SCRIPT": str(child),
            "API_SMOKE_SCRIPT": str(smoke),
            "API_RECONCILE_SCRIPT": str(reconcile),
            "COMPOSE_CANDIDATE_TRANSACTION_SCRIPT": str(transaction_driver),
            "REAL_TRANSACTION": str(TRANSACTION),
            "API_PREVIOUS_BACKEND_IMAGE": "" if discover_previous else PREVIOUS_IMAGE,
            "EXPECTED_PREVIOUS_IMAGE": PREVIOUS_IMAGE,
        },
        text=True,
        capture_output=True,
        check=False,
    )
    return result, project, order_log


@pytest.mark.parametrize("strategy", ["in_place", "blue_green"])
def test_backend_failure_cleans_candidate_and_force_reconciles_canonical(
    tmp_path,
    strategy,
):
    result, project, order_log = _backend_runner(
        tmp_path,
        strategy=strategy,
        child_exit=42,
    )

    assert result.returncode == 42
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    assert order_log.read_text(encoding="utf-8").splitlines() == [
        "flock:-n 9",
        "child:compose.yml.candidate:lock=true",
        "reconcile:compose.yml",
    ]


@pytest.mark.parametrize("strategy", ["in_place", "blue_green"])
def test_backend_promotes_only_after_candidate_smoke_succeeds(tmp_path, strategy):
    result, project, order_log = _backend_runner(tmp_path, strategy=strategy)

    assert result.returncode == 0, result.stderr
    assert "/app/google-oauth" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    assert order_log.read_text(encoding="utf-8").splitlines() == [
        "flock:-n 9",
        "child:compose.yml.candidate:lock=true",
        f"smoke:{project / 'compose.yml.candidate'}",
    ]


@pytest.mark.parametrize("strategy", ["in_place", "blue_green"])
def test_backend_smoke_failure_cleans_candidate_and_reconciles_canonical(
    tmp_path,
    strategy,
):
    result, project, order_log = _backend_runner(
        tmp_path,
        strategy=strategy,
        smoke_exit=43,
    )

    assert result.returncode == 43
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    assert order_log.read_text(encoding="utf-8").splitlines() == [
        "flock:-n 9",
        "child:compose.yml.candidate:lock=true",
        f"smoke:{project / 'compose.yml.candidate'}",
        "reconcile:compose.yml",
    ]


@pytest.mark.parametrize("strategy", ["in_place", "blue_green"])
def test_backend_promotion_failure_restores_old_image_and_canonical(
    tmp_path,
    strategy,
):
    result, project, order_log = _backend_runner(
        tmp_path,
        strategy=strategy,
        promote_exit=44,
    )

    assert result.returncode == 44
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    assert order_log.read_text(encoding="utf-8").splitlines()[-1] == "reconcile:compose.yml"


@pytest.mark.parametrize("strategy", ["in_place", "blue_green"])
def test_backend_post_rename_failure_keeps_committed_runtime_contract(
    tmp_path,
    strategy,
):
    result, project, order_log = _backend_runner(
        tmp_path,
        strategy=strategy,
        promote_after_move_exit=46,
    )

    assert result.returncode == 46
    assert "/app/google-oauth" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    assert "reconcile:compose.yml" not in order_log.read_text(encoding="utf-8")
    assert "promotion committed" in result.stderr


def test_backend_reports_critical_status_when_canonical_reconcile_fails(tmp_path):
    result, project, _ = _backend_runner(
        tmp_path,
        smoke_exit=43,
        reconcile_exit=45,
    )

    assert result.returncode == 90
    assert "CRITICAL" in result.stderr
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")


def test_backend_discovers_previous_runtime_image_from_active_slot_before_reconcile(
    tmp_path,
):
    result, project, order_log = _backend_runner(
        tmp_path,
        child_exit=42,
        discover_previous=True,
    )

    assert result.returncode == 42, result.stderr
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    commands = order_log.read_text(encoding="utf-8").splitlines()
    ps_index = next(i for i, line in enumerate(commands) if " ps -q app-green" in line)
    inspect_index = next(
        i for i, line in enumerate(commands) if line.startswith("docker:inspect --format ")
    )
    reconcile_index = commands.index("reconcile:compose.yml")
    assert ps_index < inspect_index < reconcile_index


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
    old_content = "#!/usr/bin/env python3\n# previous role agent\n"
    target.write_text(old_content, encoding="utf-8")
    target.chmod(0o755)
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
    assert not Path(env["PATRONI_ROLE_AGENT_SOURCE"]).exists()
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
    old_content = "#!/usr/bin/env python3\n# previous role agent\n"
    target.write_text(old_content, encoding="utf-8")
    target.chmod(0o755)
    env["SYSTEMCTL_FAIL_RESTART_NUMBER"] = "2"

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 90
    assert "role agent backup retained" in result.stderr
    backups = list(project.glob(".patroni-role-agent.backup.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == old_content
    assert target.read_text(encoding="utf-8") == old_content
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
