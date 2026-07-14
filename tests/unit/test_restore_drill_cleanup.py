from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLEANUP_SCRIPT = REPO_ROOT / "scripts/ha/cleanup_restore_drill_runtime.sh"
DRILL_SCRIPT = REPO_ROOT / "scripts/ha/restore_drill_latest_db.sh"


def test_cleanup_derives_every_target_from_the_guarded_operation_id():
    text = CLEANUP_SCRIPT.read_text(encoding="utf-8")

    assert '[[ "${PITR_OPERATION_ID}" =~ ^[0-9a-f]{32}$ ]]' in text
    assert 'EXPECTED_DRILL_ROOT="/var/lib/mvn-postgres-pitr/logical-restore-drills"' in text
    assert 'RUN_ID="${PITR_OPERATION_ID}"' in text
    assert 'CONTAINER="mvn-logical-restore-${RUN_ID}"' in text
    assert 'DRILL_DIR="${DRILL_ROOT}/${RUN_ID}"' in text
    for forbidden in (
        "RESTORE_DRILL_CONTAINER",
        "RESTORE_DRILL_DATA_VOLUME",
        "RESTORE_DRILL_RUN_ID",
        "KEEP_DRILL_CONTAINER",
        "KEEP_DRILL_FILES",
        "/tmp/mvn-restore-drill",
    ):
        assert forbidden not in text


def test_cleanup_removes_only_exact_labeled_runtime_objects():
    text = CLEANUP_SCRIPT.read_text(encoding="utf-8")

    assert 'api-restore-drill|${RUN_ID}' in text
    assert 'docker rm -fv "${CONTAINER}"' in text
    assert 'docker rm -f "${CONTAINER}"' not in text
    assert "container_label_mismatch" in text
    assert "container_still_exists" in text
    assert "system prune" not in text


def test_cleanup_refuses_unsafe_directory_and_unknown_artifacts():
    text = CLEANUP_SCRIPT.read_text(encoding="utf-8")

    assert '[[ -L "${DRILL_DIR}" || ! -d "${DRILL_DIR}"' in text
    assert "^0:0:700:" in text
    assert "unexpected_drill_artifact" in text
    for expected in (
        '"${DRILL_DIR}/latest.sql"',
        '"${DRILL_DIR}/latest.sql.gz"',
        '"${DRILL_DIR}/restore.sql"',
        '"${DRILL_DIR}/restore.log"',
        '"${DRILL_DIR}/container.env"',
    ):
        assert expected in text
    assert "latest-db-backup*" not in text
    assert 'rm -rf' not in text


def test_logical_drill_uses_root_state_and_isolated_generated_credentials():
    text = DRILL_SCRIPT.read_text(encoding="utf-8")

    assert 'EXPECTED_DRILL_ROOT="/var/lib/mvn-postgres-pitr/logical-restore-drills"' in text
    assert 'PITR_OPERATION_ID="${PITR_OPERATION_ID:-}"' in text
    assert 'run_id="${PITR_OPERATION_ID}"' in text
    assert 'download_container="mvn-logical-restore-download-${run_id}"' in text
    assert '--name "${download_container}"' in text
    assert '--label "com.mvn.pitr.operation=${run_id}"' in text
    assert '--network none' in text
    assert '--read-only' in text
    assert '--cap-drop ALL' in text
    assert '--security-opt no-new-privileges:true' in text
    assert '--env-file "${credentials_file}"' in text
    assert 'secrets.token_urlsafe(48)' in text
    assert "PGPASSWORD" not in text
    assert 'POSTGRES_HOST_AUTH_METHOD=trust' not in text
    assert '${POSTGRES_IMAGE:-' not in text
    assert '${APP_SERVICE:-' not in text
    assert '${DB_SERVICE:-' not in text
    assert 'POSTGRES_DATA_TMPFS_BYTES="10737418240"' in text
    assert 'POSTGRES_MEMORY_BYTES="12884901888"' in text
    assert 'POSTGRES_REQUIRED_HOST_MEMORY_BYTES="13958643712"' in text
    assert '--memory "${POSTGRES_MEMORY_BYTES}"' in text
    assert '--memory-swap "${POSTGRES_MEMORY_BYTES}"' in text
    assert 'host.get("Memory") != int(memory)' in text
    assert 'host.get("MemorySwap") != int(memory)' in text
    assert 'docker info --format \'{{.MemTotal}}\'' in text
    assert 'host_available_bytes >= POSTGRES_REQUIRED_HOST_MEMORY_BYTES' in text
    assert '--tmpfs "/var/lib/postgresql/data:rw,nosuid,nodev,size=${POSTGRES_DATA_TMPFS_BYTES}' in text
    assert 'type=volume' not in text
    assert 'data tmpfs quota is invalid' in text
    assert '--mount "type=bind,source=${sql_path},target=/restore-input.sql,readonly"' in text
    assert 'docker cp' not in text
    assert '-f /restore-input.sql' in text
    assert 'logical restore input must be the exact read-only SQL bind' in text
    assert 'ulimit -f 4096' in text
    assert 'psql -q -v ON_ERROR_STOP=1' in text
    assert 'RESTORE_TIMEOUT_SECONDS="900"' in text
    assert '--foreground --signal=TERM --kill-after=30s "${RESTORE_TIMEOUT_SECONDS}s"' in text
    assert 'docker stop --time 10 "${container}"' in text
    assert 'docker kill "${container}"' in text


def test_logical_drill_bounds_download_expansion_and_attests_runtime():
    text = DRILL_SCRIPT.read_text(encoding="utf-8")

    assert '--pitr-env-policy configured' in text
    assert 'SELECT pg_is_in_recovery()' in text
    assert '[[ "${in_recovery}" == "f" ]]' in text
    assert 'MAX_RESTORED_SQL_BYTES="8589934592"' in text
    assert 'os.statvfs' in text
    assert 'total * 2 + reserve > available' in text
    assert 'gzip.GzipFile' in text
    assert 'destination.unlink(missing_ok=True)' in text
    assert 'actual_size != size_bytes' in text
    assert 'timedelta(hours=36)' in text
    assert 'MediaIoBaseDownload' in text
    assert 'chunksize=DOWNLOAD_CHUNK_BYTES' in text
    assert 'download_backup_file' not in text
    assert 'MAX_DOWNLOAD_BYTES = 2 * 1024**3' in text
    assert 'md5Checksum' in text
