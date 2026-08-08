import re
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_PATH = REPO_ROOT / ".github/actions/notify-ha-failure/action.yml"
CHECKOUT_SHA = "df4cb1c069e1874edd31b4311f1884172cec0e10"
UPLOAD_ARTIFACT_SHA = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"

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
            if str(step.get("uses") or "").startswith("actions/upload-artifact@")
        ]

        assert artifact_indexes, workflow_path
        assert notify_index > max(artifact_indexes), workflow_path
        if workflow_path in {
            ".github/workflows/check-postgres-pitr.yml",
            ".github/workflows/postgres-pitr-restore-drill.yml",
            ".github/workflows/api-restore-drill.yml",
        }:
            assert notify_step["if"] == "failure() && github.ref == 'refs/heads/main'"
        else:
            assert notify_step["if"] == "failure()"
        assert notify_step["uses"] == "./.github/actions/notify-ha-failure"
        assert "HA_ALERT_TELEGRAM_BOT_TOKEN" in notify_step["with"]["bot-token"]
        assert "HA_ALERT_TELEGRAM_CHAT_ID" in notify_step["with"]["chat-id"]
        assert "HA_ALERT_TELEGRAM_THREAD_ID" in notify_step["with"]["thread-id"]
        assert "Artifact:" in notify_step["with"]["details"]


def test_restore_drill_checks_out_repo_before_local_alert_action():
    workflow = _yaml(REPO_ROOT / ".github/workflows/api-restore-drill.yml")
    steps = workflow["jobs"]["restore-drill"]["steps"]
    checkout_step = _step(workflow, "restore-drill", "Checkout")
    run_step = next(
        step
        for step in steps
        if step.get("name") == "Run logical restore drill on the proven Patroni primary"
    )

    assert steps[0]["name"] == "Require Reviewed Main Ref"
    assert checkout_step["uses"] == f"actions/checkout@{CHECKOUT_SHA}"
    assert checkout_step["with"] == {
        "ref": "${{ github.sha }}",
        "persist-credentials": "false",
    }
    assert workflow["concurrency"] == {
        "group": "postgres-pitr-host-operations",
        "queue": "max",
        "cancel-in-progress": "false",
    }
    assert run_step["env"] == {"SSH_KEY": "${{ secrets.SSH_KEY }}"}
    assert "python3 -I scripts/ha/run_postgres_pitr_workflow.py" in run_step["run"]
    assert "--phase logical-restore-drill" in run_step["run"]
    assert "unset SSH_KEY" in run_step["run"]
    assert "scripts/ha/restore_drill_latest_db.sh" not in run_step["run"]
    source = (REPO_ROOT / ".github/workflows/api-restore-drill.yml").read_text()
    for forbidden in ("ssh-keyscan", "accept-new", "check_patroni_production.py", "cat >", "/tmp/mvn-"):
        assert forbidden not in source


def test_restore_drill_waits_for_stable_sql_and_checks_business_data():
    script = (REPO_ROOT / "scripts/ha/restore_drill_latest_db.sh").read_text(
        encoding="utf-8"
    )

    assert "ready_streak" in script
    assert "ready_streak >= 3" in script
    assert "business_counts=" in script
    assert "product_count payment_count order_count" in script
    assert "product_count >= 1 && order_count >= 1" in script
    assert 'MIN_PUBLIC_TABLES="64"' in script
    assert "tables_count >= MIN_PUBLIC_TABLES" in script
    cleanup = (REPO_ROOT / "scripts/ha/cleanup_restore_drill_runtime.sh").read_text(
        encoding="utf-8"
    )
    assert 'docker rm -fv "${CONTAINER}"' in cleanup
    assert 'docker rm -f "${CONTAINER}"' not in cleanup
    assert "docker volume create" not in script
    assert "com.mvn.purpose=api-restore-drill" in script
    assert 'com.mvn.pitr.operation=${run_id}' in script
    assert 'drill_dir="${DRILL_ROOT}/${run_id}"' in script
    assert "PITR_OPERATION_ID must be a guarded" in script
    assert '--tmpfs "/var/lib/postgresql/data:' in script
    assert "PITR_OPERATION_ID" in cleanup
    assert "container_label_mismatch" in cleanup
    assert "cleanup_error=container_inspect_failed" in cleanup
    assert "latest-db-backup*" not in cleanup
    assert "--network none" in script
    assert "--cap-drop ALL" in script
    assert "--security-opt no-new-privileges:true" in script
    assert "--env-file" in script
    assert "PGPASSWORD" not in script
    assert "statvfs" in script
    assert 'RESOURCE_SIZING_HELPER="/usr/local/sbin/mvn-logical-restore-resource-sizer"' in script
    assert 'log "resource_envelope sql_bytes=${sql_bytes}' in script
    assert "MediaIoBaseDownload" in script
    assert "download_backup_file" not in script
    assert 'RUNTIME_CHECK_HELPER="/usr/local/sbin/mvn-postgres-pitr-runtime-check"' in script


def test_secret_bearing_restore_workflows_pin_every_external_action_to_a_commit():
    for relative in (
        ".github/workflows/check-postgres-pitr.yml",
        ".github/workflows/postgres-pitr-restore-drill.yml",
        ".github/workflows/api-restore-drill.yml",
    ):
        workflow = _yaml(REPO_ROOT / relative)
        external_actions = []
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                action = step.get("uses")
                if not action or action.startswith("./"):
                    continue
                external_actions.append(action)
                assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), (relative, action)
        assert f"actions/checkout@{CHECKOUT_SHA}" in external_actions
        assert f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}" in external_actions
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "actions/checkout@v6" not in source
        assert "actions/upload-artifact@v7" not in source
