from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DRILL_PATH = REPO_ROOT / "scripts/ha/restore_postgres_pitr_drill.sh"


def _source() -> str:
    return DRILL_PATH.read_text(encoding="utf-8")


def test_operational_drill_defaults_to_a_unique_named_restore_point():
    source = _source()

    assert 'target_mode="restore_point"' in source
    assert 'target_name="mvn_pitr_${PITR_OPERATION_ID}"' in source
    assert "pg_create_restore_point('${target_name}')" in source
    assert "pg_switch_wal()" in source
    assert '--phase wal-upload --data-dir "${archive_dir}"' in source
    assert '--target-name "${target_name}" --target-lsn "${target_lsn}"' in source
    assert 'Operational PITR drills require a complete archived WAL chain' in source
    assert 'Operational PITR drills must pause at the configured recovery target' in source
    assert 'target_mode="time"' in source
    assert 'prepare_args+=(--target-time "${TARGET_TIME}")' in source
    assert 'run_dir="${DRILL_DIR}/${PITR_OPERATION_ID}"' in source
    assert 'run_id="$(date' not in source


def test_operational_drill_binds_restore_to_live_lineage_and_archived_wal():
    source = _source()

    assert "pg_control_system() AS s CROSS JOIN pg_stat_archiver AS a" in source
    assert "s.system_identifier::text" in source
    assert "a.last_archived_wal" in source
    assert "a.last_archived_time" in source
    assert 'last_archived_epoch < target_epoch' in source
    assert '--expected-system-identifier "${live_system_identifier}"' in source
    assert '--required-end-wal "${required_end_wal}"' in source


def test_operational_drill_backfills_original_timeline_history_before_upload():
    source = _source()

    assert '"${COMPOSE[@]}" exec -T --user \\' in source
    assert '"${POSTGRES_CONTAINER_UID}:${POSTGRES_CONTAINER_GID}" \\' in source
    assert "/usr/local/bin/mvn-patroni-archive-wal" in source
    assert 'for source in "${data_dir}"/pg_wal/*.history' in source
    assert 'MAX_TIMELINE_HISTORY_FILES="1024"' in source
    assert 'if [ "${count}" -gt "${maximum}" ]' in source
    assert '"${WAL_LINEAGE_HELPER}" validate-local-history' in source
    assert '--required-end-wal "${required_end_wal}"' in source
    assert "expected_history_count" not in source
    assert "pg_control_checkpoint() AS c" not in source
    assert source.index("mvn-patroni-archive-wal") < source.index(
        '"${TOOL_RUNNER}" --phase wal-upload'
    )
    assert source.index('"${WAL_LINEAGE_HELPER}" validate-local-history') < source.index(
        '"${TOOL_RUNNER}" --phase wal-upload'
    )


def test_disposable_postgres_has_no_network_or_database_password():
    source = _source()

    assert "--network none" in source
    assert "--read-only" in source
    assert "--cap-drop ALL" in source
    assert "--security-opt no-new-privileges:true" in source
    assert "--pids-limit 256" in source
    assert "--memory 4g" in source
    assert "--cpus 2.0" in source
    assert "--tmpfs /tmp:" in source
    assert "--tmpfs /var/run/postgresql:" in source
    assert 'listen_addresses=' in source
    assert "hba_file=/pitr-control/pg_hba.conf" in source
    assert "host all all all reject" in source
    assert 'POSTGRES_CONTAINER_UID="70"' in source
    assert '-exec chmod 0400 {} +' in source
    assert "POSTGRES_PASSWORD" not in source
    assert "PGPASSWORD" not in source
    assert "NetworkSettings.Networks" not in source
    assert "docker inspect" not in source


def test_restored_config_cannot_load_backup_supplied_code_or_includes():
    source = _source()

    assert "pg_verifybackup" in source
    assert "--manifest-path=/pitr-control/backup_manifest" in source
    assert "sanitize_restored_config" in source
    assert "for name in postgresql.conf postgresql.auto.conf" in source
    assert 'path="${target_dir}/data/standby.signal"' in source
    assert "config_file=/pitr-control/postgresql.conf" in source
    assert "${target_dir}/control:/pitr-control:ro" in source
    assert "shared_preload_libraries=" in source
    assert "session_preload_libraries=" in source
    assert "local_preload_libraries=" in source
    assert "dynamic_library_path=" in source
    assert "jit=off" in source
    assert "archive_cleanup_command=" in source
    assert "recovery_end_command=" in source
    assert "ssl_passphrase_command=" in source


def test_drill_proves_target_pause_replay_lsn_and_exact_system_identifier():
    source = _source()

    assert "pg_is_wal_replay_paused()" in source
    assert "pg_last_wal_replay_lsn()" in source
    assert "pg_last_xact_replay_timestamp()" in source
    assert "current_setting('recovery_target_time')" in source
    assert "current_setting('recovery_target_name')" in source
    assert "current_setting('config_file')" in source
    assert "current_setting('hba_file')" in source
    assert "current_setting('ident_file')" in source
    assert "current_setting('data_directory')" in source
    assert 'restored_config_file}" != "/pitr-control/postgresql.conf"' in source
    assert "pg_last_wal_replay_lsn() >= '${target_lsn}'::pg_lsn" in source
    assert 'restored_system_identifier}" != "${live_system_identifier}' in source
    assert "configured_target != target_epoch" in source
    assert 'target_progress}" != "t' in source
    assert 'log "target_reached=true' in source
