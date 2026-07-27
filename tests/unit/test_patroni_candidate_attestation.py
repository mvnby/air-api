import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from tests.unit.test_patroni_candidate_transactions import (
    DEPLOY_LOCK_HELPER,
    PATRONI_RUNNER,
    TRANSACTION,
    _compose_pair,
    _executable,
    _patroni_runner_env,
    _voice_sync_env,
    _write_release_manifest,
)


def test_profile_changing_candidate_requires_official_pitr_before_any_mutation(
    tmp_path,
):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    canonical = (project / "compose.yml").read_bytes()
    (project / "compose.yml.candidate").write_bytes(
        canonical
        + b'  communications-worker:\n    environment:\n'
        + b'      COMMUNICATIONS_WORKER_ENABLED: "true"\n'
    )
    Path(env["WORKER_RUNTIME_STATE"]).touch()

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "official atomic PITR cluster migration first" in result.stderr
    assert (project / "compose.yml").read_bytes() == canonical
    assert not (project / "compose.yml.candidate").exists()
    assert not Path(env["CHILD_LOG"]).exists()
    assert not Path(env["RECONCILE_LOG"]).exists()
    assert not Path(env["PATRONI_ROLE_AGENT_TARGET"]).exists()
    assert not (project / ".ha-communications-worker-release-fenced").exists()
    assert not Path(env["VOICE_SYNC_LOG"]).exists()
    assert Path(env["WORKER_RUNTIME_STATE"]).exists()
    assert not Path(env["PATRONI_COMMAND_LOG"]).read_text(encoding="utf-8")
    assert not Path(env["SYSTEMCTL_LOG"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("operation", ["deploy", "migrate"])
def test_different_compose_is_rejected_before_either_child(tmp_path, operation):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    (project / "compose.yml.candidate").write_text(
        "services:\n  app:\n    image: changed\n",
        encoding="utf-8",
    )
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
    assert "official atomic PITR cluster migration first" in result.stderr
    assert not Path(env["CHILD_LOG"]).exists()
    assert not Path(env["RECONCILE_LOG"]).exists()
    assert not Path(env["SYSTEMCTL_LOG"]).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("profile", "enabled", "allow_all"),
    [
        ("dormant", "false", "false"),
        ("active", "true", "true"),
    ],
)
def test_identical_attested_compose_allows_same_profile_image_rollout(
    tmp_path, profile, enabled, allow_all
):
    env, project = _patroni_runner_env(tmp_path, child_exit=0)
    Path(env["WORKER_RUNTIME_STATE"]).touch()
    env.update(
        {
            "FAKE_CANONICAL_WORKER_SUPPORTED": "true",
            "FAKE_CANDIDATE_WORKER_SUPPORTED": "true",
            "FAKE_CANONICAL_WORKER_ENABLED": enabled,
            "FAKE_CANONICAL_WORKER_ALLOW_ALL": allow_all,
            "FAKE_CANDIDATE_WORKER_ENABLED": enabled,
            "FAKE_CANDIDATE_WORKER_ALLOW_ALL": allow_all,
        }
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert Path(env["CHILD_PROFILE_LOG"]).read_text(encoding="utf-8") == (
        f"{profile}|{profile}\n"
    )
    assert Path(env["RECONCILE_PROFILE_LOG"]).read_text(
        encoding="utf-8"
    ).splitlines() == [
        f"compose.yml.candidate|communications-worker|{profile}",
        f"compose.yml|communications-worker|{profile}",
    ]
    assert "/app/token.json" in (project / "compose.yml").read_text(
        encoding="utf-8"
    )


def test_failed_image_rollout_restores_the_same_active_profile(tmp_path):
    env, project = _patroni_runner_env(tmp_path, child_exit=42)
    Path(env["WORKER_RUNTIME_STATE"]).touch()
    env.update(
        {
            "FAKE_CANONICAL_WORKER_SUPPORTED": "true",
            "FAKE_CANDIDATE_WORKER_SUPPORTED": "true",
            "FAKE_CANONICAL_WORKER_ENABLED": "true",
            "FAKE_CANONICAL_WORKER_ALLOW_ALL": "true",
            "FAKE_CANDIDATE_WORKER_ENABLED": "true",
            "FAKE_CANDIDATE_WORKER_ALLOW_ALL": "true",
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
    assert Path(env["CHILD_PROFILE_LOG"]).read_text(encoding="utf-8") == (
        "active|active\n"
    )
    assert Path(env["RECONCILE_PROFILE_LOG"]).read_text(
        encoding="utf-8"
    ).splitlines() == [
        "compose.yml|app communications-worker|active",
    ]


def test_secret_is_absent_from_attestation_and_transaction_children(tmp_path):
    env, _project = _patroni_runner_env(tmp_path, child_exit=0)
    transaction_driver = tmp_path / "audited-transaction.sh"
    transaction_log = tmp_path / "transaction-actions.log"
    _executable(
        transaction_driver,
        """#!/usr/bin/env bash
set -euo pipefail
test -z "${BOT_VOICE_TRANSCRIPTION_API_KEY+x}"
test -z "${VOICE_SECRET+x}"
printf '%s\n' "$1" >> "$TRANSACTION_ACTIONS_LOG"
exec bash "$REAL_TRANSACTION" "$@"
""",
    )
    env.update(
        {
            "COMPOSE_CANDIDATE_TRANSACTION_SCRIPT": str(transaction_driver),
            "REAL_TRANSACTION": str(TRANSACTION),
            "TRANSACTION_ACTIONS_LOG": str(transaction_log),
        }
    )

    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert transaction_log.read_text(encoding="utf-8").splitlines() == [
        "stage",
        "promote",
    ]


@pytest.mark.parametrize(
    ("enabled", "allow_all"),
    [("false", "true"), ("TRUE", "false"), ("false", "FALSE")],
)
def test_candidate_rejects_noncanonical_gate_profile_before_host_mutation(
    tmp_path, enabled, allow_all
):
    env, _project = _patroni_runner_env(tmp_path, child_exit=0)
    Path(env["WORKER_RUNTIME_STATE"]).touch()
    env.update(
        {
            "FAKE_CANONICAL_WORKER_SUPPORTED": "true",
            "FAKE_CANDIDATE_WORKER_SUPPORTED": "true",
            "FAKE_CANONICAL_WORKER_ENABLED": enabled,
            "FAKE_CANONICAL_WORKER_ALLOW_ALL": allow_all,
            "FAKE_CANDIDATE_WORKER_ENABLED": enabled,
            "FAKE_CANDIDATE_WORKER_ALLOW_ALL": allow_all,
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
    assert "gate profile is not reviewed" in result.stderr
    assert not Path(env["CHILD_LOG"]).exists()
    assert not Path(env["PATRONI_ROLE_AGENT_TARGET"]).exists()
    assert Path(env["WORKER_RUNTIME_STATE"]).exists()
    assert not Path(env["SYSTEMCTL_LOG"]).read_text(encoding="utf-8")


def _run_wrong_metadata_migration(
    tmp_path, *, target_name="compose.yml.candidate", mode=None, group=None
):
    project = _compose_pair(tmp_path)
    release_manifest = _write_release_manifest(tmp_path, project)
    voice_env = _voice_sync_env(tmp_path)
    candidate = project / "compose.yml.candidate"
    target = project / target_name
    if mode is not None:
        target.chmod(mode)
    if group is not None:
        os.chown(target, -1, group)
    migration = tmp_path / "migration.sh"
    migration_log = tmp_path / "migration.log"
    _executable(migration, "#!/usr/bin/env bash\n: > \"$MIGRATION_LOG\"\n")
    result = subprocess.run(
        ["bash", str(PATRONI_RUNNER)],
        env={
            **os.environ,
            **voice_env,
            "PATRONI_CANDIDATE_OPERATION": "migrate",
            "API_PROJECT_DIR": str(project),
            "PATRONI_CANONICAL_COMPOSE_FILE": str(project / "compose.yml"),
            "PATRONI_CANDIDATE_COMPOSE_FILE": str(candidate),
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
    assert not migration_log.exists()
    assert not candidate.exists()
    return result


@pytest.mark.parametrize(
    ("target_name", "unsafe_mode"),
    [
        ("compose.yml", 0o600),
        ("compose.yml", 0o664),
        ("compose.yml", 0o755),
        ("compose.yml.candidate", 0o600),
        ("compose.yml.candidate", 0o664),
        ("compose.yml.candidate", 0o755),
    ],
)
def test_candidate_rejects_wrong_mode_before_migrate_or_runtime_mutation(
    tmp_path, target_name, unsafe_mode
):
    result = _run_wrong_metadata_migration(
        tmp_path,
        target_name=target_name,
        mode=unsafe_mode,
    )
    assert result.returncode != 0
    assert "mode 0644" in result.stderr


def test_candidate_rejects_wrong_group_before_migrate_or_runtime_mutation(
    tmp_path,
):
    alternate_group = next(
        (group for group in os.getgroups() if group != os.getegid()),
        None,
    )
    if alternate_group is None:
        pytest.skip("current user has no alternate group for metadata test")
    result = _run_wrong_metadata_migration(tmp_path, group=alternate_group)
    assert result.returncode != 0
    assert "mode 0644" in result.stderr
