import os
import hashlib
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts/ha/safe_deploy_lock.py"


def _run(lock: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(HELPER), "exec", str(lock), "/usr/bin/true"],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "API_DEPLOY_LOCK_HELPER_SHA256": hashlib.sha256(HELPER.read_bytes()).hexdigest(),
        },
    )


def test_safe_lock_rejects_symlink_without_touching_victim(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("keep", encoding="utf-8")
    victim.chmod(0o644)
    lock = tmp_path / "lock"
    lock.symlink_to(victim)

    result = _run(lock)

    assert result.returncode != 0
    assert victim.read_text(encoding="utf-8") == "keep"
    assert stat.S_IMODE(victim.stat().st_mode) == 0o644


def test_safe_lock_rejects_hardlink_before_any_permission_mutation(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("keep", encoding="utf-8")
    victim.chmod(0o644)
    lock = tmp_path / "lock"
    os.link(victim, lock)

    result = _run(lock)

    assert result.returncode != 0
    assert stat.S_IMODE(victim.stat().st_mode) == 0o644
    assert victim.stat().st_nlink == 2


def test_safe_lock_migrates_proved_legacy_0644_inode_under_lock(tmp_path):
    lock = tmp_path / "lock"
    lock.touch(mode=0o644)
    lock.chmod(0o644)

    result = _run(lock)

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    assert lock.stat().st_nlink == 1


def test_safe_lock_verify_rejects_forged_inherited_descriptor(tmp_path):
    lock = tmp_path / "lock"
    lock.touch(mode=0o600)

    result = subprocess.run(
        ["python3", str(HELPER), "verify", str(lock), "9"],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "API_DEPLOY_LOCK_HELPER_SHA256": hashlib.sha256(HELPER.read_bytes()).hexdigest(),
        },
    )

    assert result.returncode != 0
    assert "Bad file descriptor" in result.stderr


def test_candidate_and_migration_verify_inherited_lock_before_marker_check():
    candidate = (REPO_ROOT / "scripts/ha/run_patroni_candidate_transaction.sh").read_text(
        encoding="utf-8"
    )
    migration = (REPO_ROOT / "scripts/ha/run_patroni_migrations.sh").read_text(
        encoding="utf-8"
    )
    lock_index = candidate.index('"${DEPLOY_LOCK_HELPER}" verify')
    pitr_marker_index = candidate.index("require_no_pitr_maintenance", lock_index)
    marker_index = candidate.index("require_no_patroni_cutover", pitr_marker_index)
    migrate_index = candidate.index('if [[ "${OPERATION}" == "migrate" ]]', marker_index)
    assert lock_index < pitr_marker_index < marker_index < migrate_index
    assert 'API_DEPLOY_LOCK_FD="${DEPLOY_LOCK_FD}"' in candidate
    assert 'DEPLOY_LOCK_FD="${API_DEPLOY_LOCK_FD:-}"' in migration
    assert '"${DEPLOY_LOCK_HELPER}" verify' in migration


def test_candidate_rejects_writable_lock_helper_before_execution(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    helper = tmp_path / "unsafe-helper.py"
    helper.write_bytes(HELPER.read_bytes())
    helper.chmod(0o666)
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/ha/run_patroni_candidate_transaction.sh")],
        env={
            **os.environ,
            "API_PROJECT_DIR": str(project),
            "API_DEPLOY_LOCK_HELPER": str(helper),
            "API_DEPLOY_LOCK_HELPER_SHA256": hashlib.sha256(helper.read_bytes()).hexdigest(),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "metadata is unsafe" in result.stderr
    assert not (project / ".deploy.lock").exists()
