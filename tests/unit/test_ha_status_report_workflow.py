from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _workflow(path: str) -> dict:
    return yaml.load((REPO_ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(workflow: dict, step_name: str) -> dict:
    return next(step for step in workflow["jobs"]["report"]["steps"] if step.get("name") == step_name)


def test_ha_status_report_workflow_runs_scheduled_operator_rollup():
    workflow = _workflow(".github/workflows/report-ha-status.yml")

    assert workflow["name"] == "API HA Status Report"
    assert workflow["on"]["schedule"][0]["cron"] == "17 */2 * * *"
    assert "require_strict" in workflow["on"]["workflow_dispatch"]["inputs"]
    assert "skip_live" in workflow["on"]["workflow_dispatch"]["inputs"]

    job = workflow["jobs"]["report"]
    assert job["permissions"]["actions"] == "read"
    assert job["permissions"]["contents"] == "read"

    report_step = _step(workflow, "Run HA status report")
    env = report_step["env"]
    run = report_step["run"]
    assert env["GH_TOKEN"] == "${{ github.token }}"
    assert env["HA_EXTERNAL_METADATA_SOURCE"] == "env"
    assert "vars.API_DB_HA_MODE" in env["API_DB_HA_MODE"]
    assert "secrets.CLOUDFLARE_LB_READ_TOKEN" in env["CLOUDFLARE_LB_READ_TOKEN"]
    assert "vars.CLOUDFLARE_ACCOUNT_ID" in env["CLOUDFLARE_ACCOUNT_ID"]
    assert "vars.POSTGRES_PITR_REQUIRED" in env["POSTGRES_PITR_REQUIRED"]
    assert "scripts/ha/report_ha_status.py" in run
    assert "--require-strict" in run
    assert "--skip-live" in run
    assert "tee ha-status-report.log" in run

    artifact_step = _step(workflow, "Upload HA status report log")
    assert artifact_step["uses"] == "actions/upload-artifact@v7"
    assert artifact_step["with"]["path"] == "ha-status-report.log"
