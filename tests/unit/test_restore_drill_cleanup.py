import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLEANUP_SCRIPT = REPO_ROOT / "scripts/ha/cleanup_restore_drill_runtime.sh"


def _cleanup_run(
    tmp_path: Path,
    *,
    daemon_failure: bool = False,
    lowercase_absence_errors: bool = False,
    volume_remove_failure: bool = False,
    keep_container: bool = False,
    keep_files: bool = False,
    create_objects: bool = True,
    label_mismatch: bool = False,
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    container_state = tmp_path / "container.exists"
    volume_state = tmp_path / "volume.exists"
    if create_objects:
        container_state.touch()
        volume_state.touch()
    command_log = tmp_path / "docker.log"
    command_log.touch()
    docker = fake_bin / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$COMMAND_LOG"
if [[ "${DAEMON_FAILURE}" == "true" && ( "$1" == "inspect" || "$1 $2" == "volume inspect" ) ]]; then
  echo 'Cannot connect to the Docker daemon' >&2
  exit 1
fi
if [[ "$1" == "inspect" ]]; then
  if [[ "$*" == *"--format"* ]]; then
    [[ -f "$CONTAINER_STATE" ]] || exit 1
    if [[ "${LABEL_MISMATCH}" == "true" ]]; then printf 'other|other\n'; else printf 'api-restore-drill|test-run\n'; fi
    exit 0
  fi
  [[ -f "$CONTAINER_STATE" ]] && exit 0
  if [[ "${LOWERCASE_ABSENCE_ERRORS}" == "true" ]]; then
    printf '[]\nerror: no such object: drill-container\n' >&2
  else
    echo 'No such container' >&2
  fi
  exit 1
fi
if [[ "$1 $2" == "volume inspect" ]]; then
  if [[ "$*" == *"--format"* ]]; then
    [[ -f "$VOLUME_STATE" ]] || exit 1
    if [[ "${LABEL_MISMATCH}" == "true" ]]; then printf 'other|other\n'; else printf 'api-restore-drill|test-run\n'; fi
    exit 0
  fi
  [[ -f "$VOLUME_STATE" ]] && exit 0
  if [[ "${LOWERCASE_ABSENCE_ERRORS}" == "true" ]]; then
    printf '[]\nError response from daemon: get drill-volume: no such volume\n' >&2
  else
    echo 'No such volume' >&2
  fi
  exit 1
fi
if [[ "$1 $2" == "rm -fv" ]]; then
  rm -f "$CONTAINER_STATE"
  exit 0
fi
if [[ "$1 $2 $3" == "volume rm drill-volume" ]]; then
  if [[ "${VOLUME_REMOVE_FAILURE}" == "true" ]]; then exit 42; fi
  rm -f "$VOLUME_STATE"
  exit 0
fi
exit 2
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    drill_dir = tmp_path / "drill"
    drill_dir.mkdir()
    backup_file = drill_dir / "latest-db-backup.sql"
    backup_file.write_text("backup", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(CLEANUP_SCRIPT)],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "COMMAND_LOG": str(command_log),
            "CONTAINER_STATE": str(container_state),
            "VOLUME_STATE": str(volume_state),
            "DAEMON_FAILURE": str(daemon_failure).lower(),
            "LOWERCASE_ABSENCE_ERRORS": str(lowercase_absence_errors).lower(),
            "VOLUME_REMOVE_FAILURE": str(volume_remove_failure).lower(),
            "LABEL_MISMATCH": str(label_mismatch).lower(),
            "RESTORE_DRILL_CONTAINER": "drill-container",
            "RESTORE_DRILL_DATA_VOLUME": "drill-volume",
            "RESTORE_DRILL_RUN_ID": "test-run",
            "RESTORE_DRILL_DIR": str(drill_dir),
            "KEEP_DRILL_CONTAINER": str(keep_container).lower(),
            "KEEP_DRILL_FILES": str(keep_files).lower(),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    return result, container_state, volume_state, backup_file, command_log


def test_cleanup_removes_exact_runtime_and_files(tmp_path):
    result, container, volume, backup, log = _cleanup_run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert not container.exists()
    assert not volume.exists()
    assert not backup.exists()
    assert not backup.parent.exists()
    calls = log.read_text(encoding="utf-8")
    assert "rm -fv drill-container" in calls
    assert "volume rm drill-volume" in calls
    assert "system prune" not in calls


def test_cleanup_script_never_uses_a_shared_backup_glob():
    text = CLEANUP_SCRIPT.read_text(encoding="utf-8")

    assert "latest-db-backup*" not in text
    assert '"${DRILL_DIR}/latest-db-backup.sql"' in text
    assert '"${DRILL_DIR}/latest-db-backup.sql.gz"' in text
    assert 'rmdir "${DRILL_DIR}"' in text


def test_cleanup_fails_closed_when_docker_inspection_is_unavailable(tmp_path):
    result, container, volume, _, _ = _cleanup_run(tmp_path, daemon_failure=True)

    assert result.returncode != 0
    assert container.exists()
    assert volume.exists()
    assert "cleanup_error=container_inspect_failed" in result.stdout
    assert "cleanup_error=volume_inspect_failed" in result.stdout


def test_cleanup_reports_named_volume_removal_failure(tmp_path):
    result, container, volume, _, _ = _cleanup_run(
        tmp_path,
        volume_remove_failure=True,
    )

    assert result.returncode != 0
    assert not container.exists()
    assert volume.exists()
    assert "cleanup_error=volume_remove_failed" in result.stdout
    assert "cleanup_error=volume_still_exists" in result.stdout


def test_cleanup_honors_explicit_keep_flags(tmp_path):
    result, container, volume, backup, log = _cleanup_run(
        tmp_path,
        keep_container=True,
        keep_files=True,
    )

    assert result.returncode == 0
    assert container.exists()
    assert volume.exists()
    assert backup.exists()
    assert "cleanup_skipped=true" in result.stdout
    assert "rm -fv" not in log.read_text(encoding="utf-8")


def test_cleanup_accepts_already_absent_runtime(tmp_path):
    result, _, _, backup, _ = _cleanup_run(
        tmp_path,
        create_objects=False,
        lowercase_absence_errors=True,
    )

    assert result.returncode == 0
    assert not backup.exists()
    assert not backup.parent.exists()


def test_cleanup_accepts_docker_lowercase_absence_errors(tmp_path):
    result, container, volume, backup, _ = _cleanup_run(
        tmp_path,
        lowercase_absence_errors=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not container.exists()
    assert not volume.exists()
    assert not backup.exists()
    assert not backup.parent.exists()


def test_cleanup_refuses_objects_without_this_runs_labels(tmp_path):
    result, container, volume, _, log = _cleanup_run(
        tmp_path,
        label_mismatch=True,
    )

    assert result.returncode != 0
    assert container.exists()
    assert volume.exists()
    assert "cleanup_error=container_label_mismatch" in result.stdout
    assert "cleanup_error=volume_label_mismatch" in result.stdout
    calls = log.read_text(encoding="utf-8")
    assert "rm -fv drill-container" not in calls
    assert "volume rm drill-volume" not in calls
