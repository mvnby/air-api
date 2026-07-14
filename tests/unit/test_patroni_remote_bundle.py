import shutil
from pathlib import Path

import pytest

from scripts.ha.verify_patroni_remote_bundle import create_manifest, verify_bundle


REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "scripts/ha/run_patroni_candidate_transaction.sh"
LOCK_HELPER = REPO_ROOT / "scripts/ha/safe_deploy_lock.py"


def _bundle(tmp_path: Path) -> tuple[Path, str]:
    directory = tmp_path / "mvn-patroni-release.ABC12345"
    directory.mkdir(mode=0o700)
    manifest = create_manifest([WRAPPER, LOCK_HELPER])
    shutil.copy2(WRAPPER, directory / WRAPPER.name)
    shutil.copy2(LOCK_HELPER, directory / LOCK_HELPER.name)
    return directory, manifest


def test_remote_bundle_accepts_only_exact_manifest_in_private_directory(tmp_path):
    directory, manifest = _bundle(tmp_path)
    verify_bundle(directory, manifest)


def test_remote_bundle_rejects_tampered_candidate_wrapper(tmp_path):
    directory, manifest = _bundle(tmp_path)
    wrapper = directory / WRAPPER.name
    wrapper.write_bytes(wrapper.read_bytes() + b"\n# tampered\n")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        verify_bundle(directory, manifest)


def test_remote_bundle_rejects_hostile_preexisting_symlink(tmp_path):
    directory, manifest = _bundle(tmp_path)
    helper = directory / LOCK_HELPER.name
    helper.unlink()
    helper.symlink_to(LOCK_HELPER)
    with pytest.raises(RuntimeError, match="unsafe bundle file metadata"):
        verify_bundle(directory, manifest)


def test_remote_bundle_rejects_unmanifested_precreated_file(tmp_path):
    directory, manifest = _bundle(tmp_path)
    (directory / "run_patroni_migrations.sh").write_text("malicious\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="contents differ"):
        verify_bundle(directory, manifest)
