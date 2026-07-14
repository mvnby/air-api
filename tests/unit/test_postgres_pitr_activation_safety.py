import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "scripts/ha/bootstrap_postgres_pitr.sh"
INSTALLER = REPO_ROOT / "scripts/ha/install_postgres_pitr_units.sh"
EXPECTED_ARCHIVE_COMMAND = '/usr/local/bin/mvn-patroni-archive-wal "%p" "%f"'


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _write_runtime_check(fake_bin: Path) -> None:
    _write_executable(
        fake_bin / "runtime-check",
        "#!/usr/bin/env bash\n"
        "printf 'ghcr.io/mvnby/air-api/backend@sha256:%064d\\n' 0\n",
    )


def _environment(fake_bin: Path, project_dir: Path, **overrides: str) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_CONTEXT": "default",
        "RUNTIME_CHECK_HELPER": str(fake_bin / "runtime-check"),
        "PROJECT_DIR": str(project_dir),
        "COMPOSE_FILE": "docker-compose.patroni.yml",
        **overrides,
    }


def _run(script: Path, phase: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), phase],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_legacy_patroni_activation_is_hard_disabled(tmp_path):
    result = _run(
        BOOTSTRAP,
        "activate-archive",
        _environment(tmp_path, tmp_path),
    )

    assert result.returncode != 0
    assert "disabled for Patroni" in result.stderr
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert "up -d --force-recreate" not in source
    assert "CONFIRM_RECREATE_DB" not in source


def test_bootstrap_stages_final_archive_state_and_supports_late_resume():
    source = BOOTSTRAP.read_text(encoding="utf-8")
    configure_body = source.split("configure_node() {", 1)[1].split(
        "write_role_file() {", 1
    )[0]
    policy_body = source.split(
        'if [[ "${runtime_policy}" == "legacy-or-clean" ]]', 1
    )[1].split("export BACKEND_IMAGE", 1)[0]

    assert "--enable-archive" in configure_body
    assert "--disable-archive" not in configure_body
    assert "config_subtransaction_id configure-node" in configure_body
    assert "--pitr-env-policy legacy-migration" in policy_body
    assert "--pitr-env-policy migration-files-clean" in policy_body
    assert "--pitr-env-policy configured" in policy_body


def test_bootstrap_provisions_host_state_only_inside_root_transaction_phase():
    source = BOOTSTRAP.read_text(encoding="utf-8")
    body = source.split("provision_node() {", 1)[1].split(
        "configure_node() {", 1
    )[0]

    assert 'require_transaction_id' in body
    assert 'require_active_patroni_compose legacy-or-clean' in body
    assert 'require_executable "${PROVISION_HELPER}"' in body
    assert '--transaction-id "${PITR_TRANSACTION_ID}"' in body
    assert 'provision-node)' in source


def test_bootstrap_rejects_non_patroni_compose_before_docker(tmp_path):
    result = _run(
        BOOTSTRAP,
        "verify",
        _environment(
            tmp_path,
            tmp_path,
            COMPOSE_FILE="docker-compose.prod.yml",
        ),
    )

    assert result.returncode != 0
    assert "refusing non-Patroni compose file" in result.stderr


def test_installer_rejects_non_patroni_compose_before_host_writes(tmp_path):
    source = INSTALLER.read_text(encoding="utf-8")
    validation = source.index("COMPOSE_FILE must be docker-compose.patroni.yml")
    first_install = source.index("install -o root -g root")
    assert validation < first_install
    assert 'COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"' not in source


def test_installer_never_enables_timers_directly(tmp_path):
    source = INSTALLER.read_text(encoding="utf-8")
    rejection = source.index("installer never enables PITR timers")
    first_install = source.index("install -o root -g root")
    assert rejection < first_install
    assert "PITR_INSTALL_LOCK_HELD" not in source


def test_installer_keeps_blue_green_and_safe_lock_helper_in_one_libexec_generation():
    source = INSTALLER.read_text(encoding="utf-8")
    for asset in (
        "deploy_backend_blue_green.sh",
        "deploy_backend_blue_green_safety.sh",
        "prepare_google_oauth_token_dir.sh",
        "safe_deploy_lock.py",
    ):
        assert f"/usr/local/libexec/mvn-pitr/{asset}" in source


def test_bootstrap_rejects_same_project_container_from_wrong_compose(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "docker-compose.patroni.yml").write_text("services: {}\n")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_runtime_check(fake_bin)
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
case "$*" in
  "compose version") exit 0 ;;
  *"compose -f docker-compose.patroni.yml ps -q db"*) printf 'db-container\\n' ;;
  "inspect --format"*) printf '/wrong/docker-compose.prod.yml\\n' ;;
  *) exit 70 ;;
esac
""",
    )

    result = _run(BOOTSTRAP, "verify", _environment(fake_bin, project_dir))

    assert result.returncode != 0
    assert "is not managed only by" in result.stderr
    assert "docker-compose.patroni.yml" in result.stderr


def test_bootstrap_rejects_patroni_compose_with_unreviewed_override(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    patroni_compose = project_dir / "docker-compose.patroni.yml"
    patroni_compose.write_text("services: {}\n")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_runtime_check(fake_bin)
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env bash
case "$*" in
  "compose version") exit 0 ;;
  *"compose -f docker-compose.patroni.yml ps -q db"*) printf 'db-container\\n' ;;
  "inspect --format"*) printf '{patroni_compose},/tmp/unreviewed.yml\\n' ;;
  *) exit 70 ;;
esac
""",
    )

    result = _run(BOOTSTRAP, "verify", _environment(fake_bin, project_dir))

    assert result.returncode != 0
    assert "is not managed only by" in result.stderr


def _runtime_fakes(
    tmp_path: Path, *, status_exit: int, archive_timeout: str = "300"
) -> tuple[Path, Path, Path, Path, Path]:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "docker-compose.patroni.yml").write_text("services: {}\n")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    target_config = project_dir / "docker-compose.patroni.yml"
    pitr_env = tmp_path / "mvn-postgres-pitr.env"
    pitr_env.write_text(
        f"PROJECT_DIR={project_dir}\nCOMPOSE_FILE=docker-compose.patroni.yml\n",
        encoding="utf-8",
    )
    unit_dir = tmp_path / "systemd"
    unit_dir.mkdir()
    for unit in (
        "mvn-postgres-wal-upload.service",
        "mvn-postgres-wal-upload.timer",
        "mvn-postgres-basebackup.service",
        "mvn-postgres-basebackup.timer",
    ):
        if unit == "mvn-postgres-wal-upload.service":
            phase = "wal-upload"
            timeout = "15min"
            stop_timeout = "30s"
        elif unit == "mvn-postgres-basebackup.service":
            phase = "basebackup"
            timeout = "2h"
            stop_timeout = "2min"
        else:
            phase = ""
            timeout = ""
            stop_timeout = ""
        content = "[Timer]\nOnCalendar=hourly\n"
        if phase:
            reliability = "SuccessExitStatus=75\n"
            if phase == "basebackup":
                reliability = "Restart=on-failure\nRestartSec=5min\n"
            content = (
                f"[Service]\nEnvironmentFile={pitr_env}\n"
                f"{reliability}"
                f"TimeoutStartSec={timeout}\n"
                f"TimeoutStopSec={stop_timeout}\n"
                "KillMode=control-group\n"
                "ExecStart=/usr/bin/env -i "
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
                "HOME=/root LANG=C LC_ALL=C /usr/bin/python3 -I "
                "/usr/local/sbin/mvn-postgres-pitr-scheduled-runner "
                f"--phase {phase} --project-dir ${{PROJECT_DIR}} "
                "--compose-file ${COMPOSE_FILE}\n"
            )
        (unit_dir / unit).write_text(
            content,
            encoding="utf-8",
        )
    _write_executable(fake_bin / "id", "#!/usr/bin/env bash\nprintf '0\\n'\n")
    _write_runtime_check(fake_bin)
    _write_executable(
        fake_bin / "stat",
        """#!/usr/bin/env bash
case "$2" in
  %u) printf '0\n' ;;
  %a|%Lp) printf '600\n' ;;
  *) exit 70 ;;
esac
""",
    )
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env bash
case "$*" in
  "compose version") exit 0 ;;
  *"compose -f docker-compose.patroni.yml ps -q db"*) printf 'db-container\\n' ;;
  "inspect --format"*) printf '{target_config}\\n' ;;
  *"SELECT pg_is_in_recovery"*) printf 'f\\n' ;;
  *"archive_mode"*) printf 'on\\n' ;;
  *"archive_timeout"*) printf '{archive_timeout}\\n' ;;
  *"archive_command"*) printf '%s\\n' '{EXPECTED_ARCHIVE_COMMAND}' ;;
  *) exit 70 ;;
esac
""",
    )
    _write_executable(
        fake_bin / "systemctl",
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SYSTEMCTL_LOG"
case "$1" in
  show)
    case "$2" in
      --property=FragmentPath) printf '%s/%s\n' "$PITR_SYSTEMD_UNIT_DIR" "$4" ;;
      --property=DropInPaths) printf '%s\n' "${SYSTEMD_DROP_INS:-}" ;;
      --property=NeedDaemonReload) printf '%s\n' "${SYSTEMD_NEED_RELOAD:-no}" ;;
      *) exit 70 ;;
    esac
    ;;
  is-active)
    printf '%s\n' "${SYSTEMCTL_ACTIVE_STATE:-inactive}"
    [[ "${SYSTEMCTL_ACTIVE_STATE:-inactive}" == "active" ]] && exit 0
    [[ "${SYSTEMCTL_ACTIVE_STATE:-inactive}" == "inactive" ]] && exit 3
    exit 1
    ;;
  is-enabled)
    printf '%s\n' "${SYSTEMCTL_ENABLED_STATE:-disabled}"
    [[ "${SYSTEMCTL_ENABLED_STATE:-disabled}" == "enabled" ]] && exit 0
    [[ "${SYSTEMCTL_ENABLED_STATE:-disabled}" == "disabled" ]] && exit 1
    exit 1
    ;;
  enable)
    if [[ "${2:-}" == "--now" ]]; then
      exit "${SYSTEMCTL_ENABLE_EXIT:-0}"
    fi
    exit "${SYSTEMCTL_ROLLBACK_EXIT:-0}"
    ;;
  disable|start|stop) exit "${SYSTEMCTL_ROLLBACK_EXIT:-0}" ;;
esac
exit 0
""",
    )
    status = tmp_path / "status"
    _write_executable(
        status,
        f"""#!/usr/bin/env bash
printf 'required=%s project=%s compose=%s\\n' \
  "$PITR_REQUIRED" "$PROJECT_DIR" "$COMPOSE_FILE" >> "$STATUS_LOG"
exit {status_exit}
""",
    )
    return fake_bin, project_dir, status, pitr_env, unit_dir


def test_enable_timers_rolls_back_when_strict_verification_fails(tmp_path):
    fake_bin, project_dir, status, pitr_env, unit_dir = _runtime_fakes(
        tmp_path, status_exit=23
    )
    systemctl_log = tmp_path / "systemctl.log"
    status_log = tmp_path / "status.log"
    result = _run(
        BOOTSTRAP,
        "enable-timers",
        _environment(
            fake_bin,
            project_dir,
            STATUS_HELPER=str(status),
            SYSTEMCTL_LOG=str(systemctl_log),
            STATUS_LOG=str(status_log),
            PITR_SYSTEMD_ENV_FILE=str(pitr_env),
            PITR_SYSTEMD_UNIT_DIR=str(unit_dir),
        ),
    )

    assert result.returncode != 0
    calls = systemctl_log.read_text(encoding="utf-8").splitlines()
    assert "enable --now mvn-postgres-wal-upload.timer mvn-postgres-basebackup.timer" in calls
    assert "disable mvn-postgres-wal-upload.timer" in calls
    assert "stop mvn-postgres-wal-upload.timer" in calls
    assert "disable mvn-postgres-basebackup.timer" in calls
    assert "stop mvn-postgres-basebackup.timer" in calls
    assert "previous timer state was restored" in result.stderr


def test_enable_timers_keeps_preexisting_active_state_on_failure(tmp_path):
    fake_bin, project_dir, status, pitr_env, unit_dir = _runtime_fakes(
        tmp_path, status_exit=23
    )
    systemctl_log = tmp_path / "systemctl.log"
    status_log = tmp_path / "status.log"
    result = _run(
        BOOTSTRAP,
        "enable-timers",
        _environment(
            fake_bin,
            project_dir,
            STATUS_HELPER=str(status),
            SYSTEMCTL_LOG=str(systemctl_log),
            STATUS_LOG=str(status_log),
            SYSTEMCTL_ACTIVE_STATE="active",
            SYSTEMCTL_ENABLED_STATE="enabled",
            PITR_SYSTEMD_ENV_FILE=str(pitr_env),
            PITR_SYSTEMD_UNIT_DIR=str(unit_dir),
        ),
    )

    assert result.returncode != 0
    calls = systemctl_log.read_text(encoding="utf-8").splitlines()
    assert "enable mvn-postgres-wal-upload.timer" in calls
    assert "start mvn-postgres-wal-upload.timer" in calls
    assert "enable mvn-postgres-basebackup.timer" in calls
    assert "start mvn-postgres-basebackup.timer" in calls
    assert not any(call.startswith("disable ") for call in calls)
    assert "stop mvn-postgres-wal-upload.service" in calls
    assert "stop mvn-postgres-basebackup.service" in calls
    assert "start mvn-postgres-wal-upload.service" in calls
    assert "start mvn-postgres-basebackup.service" in calls


def test_enable_timers_passes_exact_target_to_strict_verification(tmp_path):
    fake_bin, project_dir, status, pitr_env, unit_dir = _runtime_fakes(
        tmp_path, status_exit=0
    )
    systemctl_log = tmp_path / "systemctl.log"
    status_log = tmp_path / "status.log"
    result = _run(
        BOOTSTRAP,
        "enable-timers",
        _environment(
            fake_bin,
            project_dir,
            STATUS_HELPER=str(status),
            SYSTEMCTL_LOG=str(systemctl_log),
            STATUS_LOG=str(status_log),
            PITR_SYSTEMD_ENV_FILE=str(pitr_env),
            PITR_SYSTEMD_UNIT_DIR=str(unit_dir),
        ),
    )

    assert result.returncode == 0, result.stderr
    assert status_log.read_text(encoding="utf-8").strip() == (
        f"required=true project={project_dir} compose=docker-compose.patroni.yml"
    )
    calls = systemctl_log.read_text(encoding="utf-8").splitlines()
    assert any(call.startswith("enable --now") for call in calls)
    assert not any(call.startswith(("disable ", "stop ")) for call in calls)


def test_partial_timer_enable_failure_restores_initial_state(tmp_path):
    fake_bin, project_dir, status, pitr_env, unit_dir = _runtime_fakes(
        tmp_path, status_exit=0
    )
    systemctl_log = tmp_path / "systemctl.log"
    status_log = tmp_path / "status.log"
    result = _run(
        BOOTSTRAP,
        "enable-timers",
        _environment(
            fake_bin,
            project_dir,
            STATUS_HELPER=str(status),
            SYSTEMCTL_LOG=str(systemctl_log),
            STATUS_LOG=str(status_log),
            SYSTEMCTL_ENABLE_EXIT="19",
            PITR_SYSTEMD_ENV_FILE=str(pitr_env),
            PITR_SYSTEMD_UNIT_DIR=str(unit_dir),
        ),
    )

    assert result.returncode != 0
    calls = systemctl_log.read_text(encoding="utf-8").splitlines()
    assert "disable mvn-postgres-wal-upload.timer" in calls
    assert "stop mvn-postgres-wal-upload.timer" in calls
    assert "disable mvn-postgres-basebackup.timer" in calls
    assert "stop mvn-postgres-basebackup.timer" in calls
    assert not status_log.exists()
    assert "timer enable failed; previous timer state was restored" in result.stderr


def test_verify_rejects_archive_timeout_drift(tmp_path):
    fake_bin, project_dir, status, _pitr_env, _unit_dir = _runtime_fakes(
        tmp_path,
        status_exit=0,
        archive_timeout="600",
    )
    result = _run(
        BOOTSTRAP,
        "verify",
        _environment(
            fake_bin,
            project_dir,
            STATUS_HELPER=str(status),
            STATUS_LOG=str(tmp_path / "status.log"),
        ),
    )

    assert result.returncode != 0
    assert "reviewed 300 seconds" in result.stderr


def test_enable_timers_rejects_mismatched_systemd_environment(tmp_path):
    fake_bin, project_dir, status, pitr_env, unit_dir = _runtime_fakes(
        tmp_path, status_exit=0
    )
    pitr_env.write_text(
        f"PROJECT_DIR={project_dir}\nCOMPOSE_FILE=docker-compose.prod.yml\n",
        encoding="utf-8",
    )
    systemctl_log = tmp_path / "systemctl.log"
    result = _run(
        BOOTSTRAP,
        "enable-timers",
        _environment(
            fake_bin,
            project_dir,
            STATUS_HELPER=str(status),
            STATUS_LOG=str(tmp_path / "status.log"),
            SYSTEMCTL_LOG=str(systemctl_log),
            PITR_SYSTEMD_ENV_FILE=str(pitr_env),
            PITR_SYSTEMD_UNIT_DIR=str(unit_dir),
        ),
    )

    assert result.returncode != 0
    assert "does not match the selected Patroni node" in result.stderr
    calls = systemctl_log.read_text(encoding="utf-8").splitlines()
    assert calls == ["daemon-reload"]


def test_unit_files_require_exact_environment_without_legacy_defaults():
    for path in (
        REPO_ROOT / "deploy/ha/systemd/mvn-postgres-wal-upload.service",
        REPO_ROOT / "deploy/ha/systemd/mvn-postgres-basebackup.service",
    ):
        source = path.read_text(encoding="utf-8")
        assert "EnvironmentFile=/etc/mvn-postgres-pitr.env" in source
        assert "EnvironmentFile=-" not in source
        assert "docker-compose.prod.yml" not in source
        assert "Environment=PROJECT_DIR=" not in source


def test_legacy_combined_bootstrap_phase_is_hard_disabled(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    compose = project_dir / "docker-compose.patroni.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    env_file = project_dir / ".env"
    env_file.write_text("POSTGRES_PITR_ARCHIVE_MODE=on\n", encoding="utf-8")
    env_file.chmod(0o600)
    input_env = tmp_path / "input.env"
    input_env.write_text("POSTGRES_PITR_CLUSTER=mvn-api\n", encoding="utf-8")
    input_env.chmod(0o600)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runtime_log = tmp_path / "runtime.log"
    backup_log = tmp_path / "backup.log"
    _write_executable(fake_bin / "id", "#!/usr/bin/env bash\nprintf '0\\n'\n")
    _write_executable(
        fake_bin / "stat",
        "#!/usr/bin/env bash\nprintf '600\\n'\n",
    )
    _write_executable(
        fake_bin / "runtime-check",
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$RUNTIME_LOG\"\n"
        "printf 'ghcr.io/mvnby/air-api/backend@sha256:%064d\\n' 0\n",
    )
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env bash
case "$*" in
  "compose version") exit 0 ;;
  *"compose -f docker-compose.patroni.yml ps -q db"*) printf 'db-container\\n' ;;
  "inspect --format"*) printf '{compose}\\n' ;;
  *"SELECT pg_is_in_recovery"*) printf 'f\\n' ;;
  *"pg_settings"*)
    printf 'archive_command|{EXPECTED_ARCHIVE_COMMAND}\\narchive_mode|on\\narchive_timeout|300\\n'
    ;;
  *) exit 70 ;;
esac
""",
    )
    configure = tmp_path / "configure.py"
    _write_executable(
        configure,
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n"
        "project = Path(sys.argv[sys.argv.index('--project-dir') + 1])\n"
        "if '--dry-run' in sys.argv:\n"
        "    print('dry-run validated')\n"
        "    raise SystemExit(0)\n"
        "path = project / '.env'\n"
        "mode = 'on' if '--enable-archive' in sys.argv else 'off'\n"
        "path.write_text(f'POSTGRES_PITR_ARCHIVE_MODE={mode}\\n', encoding='utf-8')\n",
    )
    basebackup = tmp_path / "basebackup"
    _write_executable(
        basebackup,
        "#!/usr/bin/env bash\n"
        "mode=$(sed -n 's/^POSTGRES_PITR_ARCHIVE_MODE=//p' \"$PROJECT_DIR/.env\")\n"
        "printf 'policy=%s mode=%s\\n' \"$PITR_RUNTIME_POLICY\" \"$mode\" >> \"$BACKUP_LOG\"\n",
    )
    helpers = {}
    for name in ("wal", "status", "restore"):
        helper = tmp_path / name
        _write_executable(helper, "#!/usr/bin/env bash\nexit 0\n")
        helpers[name] = helper

    result = _run(
        BOOTSTRAP,
        "bootstrap-before-maintenance",
        _environment(
            fake_bin,
            project_dir,
            ENV_INPUT_FILE=str(input_env),
            CONFIGURE_HELPER=str(configure),
            BASEBACKUP_HELPER=str(basebackup),
            WAL_UPLOAD_HELPER=str(helpers["wal"]),
            STATUS_HELPER=str(helpers["status"]),
            RESTORE_DRILL_HELPER=str(helpers["restore"]),
            RUNTIME_LOG=str(runtime_log),
            BACKUP_LOG=str(backup_log),
        ),
    )

    assert result.returncode != 0
    assert "legacy combined PITR phases are disabled" in result.stderr
    assert not backup_log.exists()
    assert not runtime_log.exists()


def test_scrub_node_uses_attested_inherited_deploy_lock_without_tmp_summary():
    source = BOOTSTRAP.read_text(encoding="utf-8")
    scrub = source.split("scrub_node() {", 1)[1].split("enable_archive_env() {", 1)[0]
    assert "API_DEPLOY_LOCK_ALREADY_HELD" not in scrub
    assert '[[ "${DEPLOY_LOCK_FD}" == "9" ]]' in scrub
    assert '"${DEPLOY_LOCK_HELPER}" verify' in scrub
    for variable in (
        "API_DEPLOY_LOCK_FD",
        "API_DEPLOY_LOCK_FILE",
        "API_DEPLOY_LOCK_HELPER",
        "API_DEPLOY_LOCK_HELPER_SHA256",
    ):
        assert variable in scrub
    assert "API_BLUE_GREEN_SUMMARY_FILE=/dev/null" in scrub
    assert "/tmp/backend_blue_green_summary" not in scrub
