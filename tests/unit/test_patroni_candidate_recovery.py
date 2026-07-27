import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from tests.unit.test_patroni_candidate_transactions import (
    DEPLOY_LOCK_HELPER,
    PATRONI_RUNNER,
    REPO_ROOT,
    TRANSACTION,
    _compose_pair,
    _executable,
    _patroni_runner_env,
    _voice_sync_env,
    _write_release_manifest,
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


@pytest.mark.parametrize("migration_exit", [0, 48])
def test_patroni_migration_always_cleans_candidate_without_promoting(
    tmp_path,
    migration_exit,
):
    project = _compose_pair(tmp_path)
    release_manifest = _write_release_manifest(tmp_path, project)
    voice_env = _voice_sync_env(tmp_path)
    old = (project / "compose.yml").read_text(encoding="utf-8")
    migration_log = tmp_path / "migration.log"
    migration = tmp_path / "migration.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    _executable(
        migration,
        f"""#!/usr/bin/env bash
set -euo pipefail
test -z "${{BOT_VOICE_TRANSCRIPTION_API_KEY+x}}"
test -f "$VOICE_SYNC_LOG"
printf '%s\n' "$API_COMPOSE_FILE" > "$MIGRATION_LOG"
exit {migration_exit}
""",
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env={
            **os.environ,
            **voice_env,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "PATRONI_CANDIDATE_OPERATION": "migrate",
            "API_PROJECT_DIR": str(project),
            "PATRONI_CANONICAL_COMPOSE_FILE": str(project / "compose.yml"),
            "PATRONI_CANDIDATE_COMPOSE_FILE": str(project / "compose.yml.candidate"),
            "PATRONI_FINALIZED_RELEASE_MANIFEST": str(release_manifest),
            "COMPOSE_CANDIDATE_TRANSACTION_SCRIPT": str(TRANSACTION),
            "PATRONI_MIGRATION_SCRIPT": str(migration),
            "MIGRATION_LOG": str(migration_log),
            "API_DEPLOY_LOCK_HELPER": str(DEPLOY_LOCK_HELPER),
            "API_DEPLOY_LOCK_HELPER_SHA256": hashlib.sha256(
                DEPLOY_LOCK_HELPER.read_bytes()
            ).hexdigest(),
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


@pytest.mark.parametrize("operation", ["deploy", "migrate"])
def test_patroni_candidate_rejects_database_rollout_marker_before_mutation(
    tmp_path, operation
):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    marker = project / ".patroni-cutover-in-progress"
    marker.write_text("0" * 32 + "\n", encoding="ascii")
    env["PATRONI_CANDIDATE_OPERATION"] = operation
    if operation == "migrate":
        env["PATRONI_MIGRATION_SCRIPT"] = env["PATRONI_DEPLOY_SCRIPT"]

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Patroni database rollout is in progress" in result.stderr
    assert not (tmp_path / "child.log").exists()
    assert "/app/token.json" in (project / "compose.yml").read_text(encoding="utf-8")
