import hashlib
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSACTION = REPO_ROOT / "scripts/compose_candidate_transaction.sh"
BACKEND_RUNNER = REPO_ROOT / "scripts/deploy_backend_candidate_transaction.sh"
RECONCILE_RUNTIME = REPO_ROOT / "scripts/reconcile_backend_compose_runtime.sh"
LOCK_HELPER = REPO_ROOT / "scripts/ha/safe_deploy_lock.py"
LOCK_HELPER_SHA256 = hashlib.sha256(LOCK_HELPER.read_bytes()).hexdigest()
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
    use_real_reconcile: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    project = _compose_pair(tmp_path)
    if discover_previous:
        (project / ".active-api-slot").write_text("green\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
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
elif [[ "$1" == "compose" && "$*" == *" up -d --no-deps --force-recreate app" ]]; then
  exit 0
else
  exit 91
fi
""",
    )
    _executable(
        fake_bin / "curl",
        "#!/usr/bin/env bash\nprintf '{\"status\":\"ok\"}\\n'\n",
    )
    child = tmp_path / "deploy-child.sh"
    _executable(
        child,
        f"""#!/usr/bin/env bash
set -euo pipefail
grep -Fq '/app/token.json' "$API_PROJECT_DIR/compose.yml"
grep -Fq '/app/google-oauth' "$API_PROJECT_DIR/$API_COMPOSE_FILE"
printf 'child:%s:fd=%s\n' "$API_COMPOSE_FILE" "${{API_DEPLOY_LOCK_FD:-}}" >> "$ORDER_LOG"
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
    reconcile = RECONCILE_RUNTIME if use_real_reconcile else tmp_path / "reconcile.sh"
    if not use_real_reconcile:
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
            "API_DEPLOY_LOCK_HELPER": str(LOCK_HELPER),
            "API_DEPLOY_LOCK_HELPER_SHA256": LOCK_HELPER_SHA256,
            "COMMUNICATIONS_WORKER_RELEASE_HELPER": str(
                tmp_path / "intentionally-absent-worker-helper.sh"
            ),
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
        "child:compose.yml.candidate:fd=9",
        "reconcile:compose.yml",
    ]


def test_legacy_app_only_failure_rollback_does_not_require_worker_helper(tmp_path):
    result, project, order_log = _backend_runner(
        tmp_path,
        child_exit=42,
        use_real_reconcile=True,
    )

    assert result.returncode == 42, result.stderr
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    commands = order_log.read_text(encoding="utf-8")
    assert "child:compose.yml.candidate:fd=9" in commands
    assert "up -d --no-deps --force-recreate app" in commands
    assert "communications-worker" not in commands


@pytest.mark.parametrize("strategy", ["in_place", "blue_green"])
def test_backend_promotes_only_after_candidate_smoke_succeeds(tmp_path, strategy):
    result, project, order_log = _backend_runner(tmp_path, strategy=strategy)

    assert result.returncode == 0, result.stderr
    assert "/app/google-oauth" in (project / "compose.yml").read_text(encoding="utf-8")
    assert not (project / "compose.yml.candidate").exists()
    assert order_log.read_text(encoding="utf-8").splitlines() == [
        "child:compose.yml.candidate:fd=9",
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
        "child:compose.yml.candidate:fd=9",
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
