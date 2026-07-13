from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_PATH = REPO_ROOT / ".github/actions/notify-ha-failure/action.yml"

ALERTED_WORKFLOWS = [
    (".github/workflows/api-restore-drill.yml", "restore-drill"),
    (".github/workflows/check-api-ha-invariants.yml", "check"),
    (".github/workflows/check-api-ha-readiness.yml", "audit"),
    (".github/workflows/check-api-vps-health.yml", "check"),
    (".github/workflows/check-cloudflare-lb-config.yml", "check"),
    (".github/workflows/check-media-cdn.yml", "check"),
    (".github/workflows/check-postgres-pitr.yml", "check"),
    (".github/workflows/check-postgres-replication.yml", "check"),
    (".github/workflows/postgres-pitr-restore-drill.yml", "pitr-restore-drill"),
    (".github/workflows/report-ha-status.yml", "report"),
]


def _yaml(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(workflow: dict, job_name: str, step_name: str) -> dict:
    return next(step for step in workflow["jobs"][job_name]["steps"] if step.get("name") == step_name)


def test_notify_ha_failure_action_skips_when_telegram_secrets_are_absent():
    action = _yaml(ACTION_PATH)
    step = action["runs"]["steps"][0]
    run = step["run"]

    assert action["runs"]["using"] == "composite"
    assert "HA_ALERT_TELEGRAM_BOT_TOKEN or HA_ALERT_TELEGRAM_CHAT_ID is not configured" in run
    assert "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" in run
    assert "GITHUB_RUN_ID" in run
    assert "disable_web_page_preview" in run


def test_ha_monitor_workflows_notify_on_failure_after_artifact_upload():
    for workflow_path, job_name in ALERTED_WORKFLOWS:
        workflow = _yaml(REPO_ROOT / workflow_path)
        steps = workflow["jobs"][job_name]["steps"]
        notify_step = _step(workflow, job_name, "Notify HA failure")
        notify_index = steps.index(notify_step)
        artifact_indexes = [
            index
            for index, step in enumerate(steps)
            if step.get("uses") == "actions/upload-artifact@v7"
        ]

        assert artifact_indexes, workflow_path
        assert notify_index > max(artifact_indexes), workflow_path
        assert notify_step["if"] == "failure()"
        assert notify_step["uses"] == "./.github/actions/notify-ha-failure"
        assert "HA_ALERT_TELEGRAM_BOT_TOKEN" in notify_step["with"]["bot-token"]
        assert "HA_ALERT_TELEGRAM_CHAT_ID" in notify_step["with"]["chat-id"]
        assert "HA_ALERT_TELEGRAM_THREAD_ID" in notify_step["with"]["thread-id"]
        assert "Artifact:" in notify_step["with"]["details"]


def test_restore_drill_checks_out_repo_before_local_alert_action():
    workflow = _yaml(REPO_ROOT / ".github/workflows/api-restore-drill.yml")
    steps = workflow["jobs"]["restore-drill"]["steps"]
    setup_step = next(step for step in steps if step.get("name") == "Setup API SSH Key")
    run_step = next(
        step for step in steps if step.get("name") == "Run restore drill on current API primary"
    )

    assert steps[0]["name"] == "Checkout"
    assert steps[0]["uses"] == "actions/checkout@v6"
    assert workflow["concurrency"] == {
        "group": "api-restore-drill",
        "cancel-in-progress": "false",
    }
    assert "API_STANDBY_HOST" in setup_step["env"]
    assert 'ssh-keyscan -T 10 -H "${API_STANDBY_HOST}"' in setup_step["run"]
    assert "API_DB_HA_MODE" in run_step["env"]
    assert "API_STANDBY_PROJECT_DIR" in run_step["env"]
    assert "check_patroni_production.py --resolve-primary" in run_step["run"]
    assert "scripts/ha/restore_drill_latest_db.sh" in run_step["run"]
    assert "scripts/ha/cleanup_restore_drill_runtime.sh" in run_step["run"]
    assert "RESTORE_DRILL_CLEANUP_SCRIPT=" in run_step["run"]
    assert 'selected_node=${target_label} ha_mode=${API_DB_HA_MODE}' in run_step["run"]


def test_restore_drill_waits_for_stable_sql_and_checks_business_data():
    script = (REPO_ROOT / "scripts/ha/restore_drill_latest_db.sh").read_text(
        encoding="utf-8"
    )

    assert "ready_streak" in script
    assert '"${ready_streak}" -ge 3' in script
    assert "business_counts=" in script
    assert "product_count payment_count order_count" in script
    assert '"${product_count}" -lt 1 || "${order_count}" -lt 1' in script
    assert 'MIN_PUBLIC_TABLES="${MIN_PUBLIC_TABLES:-64}"' in script
    assert '"${tables_count}" -lt "${MIN_PUBLIC_TABLES}"' in script
    cleanup = (REPO_ROOT / "scripts/ha/cleanup_restore_drill_runtime.sh").read_text(
        encoding="utf-8"
    )
    assert 'docker rm -fv "${CONTAINER}"' in cleanup
    assert 'docker rm -f "${CONTAINER}"' not in cleanup
    assert "docker volume create" in script
    assert "com.mvn.purpose=api-restore-drill" in script
    assert 'com.mvn.run_id=${run_id}' in script
    assert 'DRILL_DIR="${DRILL_ROOT}/${run_id}"' in script
    assert "RESTORE_DRILL_RUN_ID must contain only" in script
    assert 'source=${data_volume},target=/var/lib/postgresql/data' in script
    assert 'docker volume rm "${DATA_VOLUME}"' in cleanup
    assert 'docker volume rm -f "${DATA_VOLUME}"' not in cleanup
    assert "RESTORE_DRILL_RUN_ID" in cleanup
    assert "container_label_mismatch" in cleanup
    assert "volume_label_mismatch" in cleanup
    assert "cleanup_error=${kind}_inspect_failed" in cleanup
    assert "latest-db-backup*" not in cleanup
