from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _workflow(path: str) -> dict:
    return yaml.load((REPO_ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(workflow: dict, job_name: str, step_name: str) -> dict:
    steps = workflow["jobs"][job_name]["steps"]
    return next(step for step in steps if step.get("name") == step_name)


def test_postgres_pitr_check_workflow_preserves_strict_remote_gate():
    workflow = _workflow(".github/workflows/check-postgres-pitr.yml")
    dispatch_inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    check_step = _step(workflow, "check", "Run PostgreSQL PITR Check")
    summary_step = _step(workflow, "check", "Write Summary")
    artifact_step = _step(workflow, "check", "Upload PITR Check Log")

    assert dispatch_inputs["required"]["default"] == "false"
    assert "Fail if PITR is not fully enabled" in dispatch_inputs["required"]["description"]
    assert "POSTGRES_PITR_REQUIRED" in check_step["env"]["PITR_REQUIRED"]
    assert "POSTGRES_PITR_MAX_WAL_AGE_MINUTES" in check_step["env"]["PITR_MAX_WAL_AGE_MINUTES"]
    assert "POSTGRES_PITR_MAX_BASEBACKUP_AGE_HOURS" in check_step["env"]["PITR_MAX_BASEBACKUP_AGE_HOURS"]
    assert "scripts/ha/check_postgres_pitr_status.sh" in check_step["run"]
    assert 'PITR_REQUIRED=$(quote "${PITR_REQUIRED}")' in check_step["run"]
    assert 'PITR_MAX_WAL_AGE_MINUTES=$(quote "${PITR_MAX_WAL_AGE_MINUTES}")' in check_step["run"]
    assert 'PITR_MAX_BASEBACKUP_AGE_HOURS=$(quote "${PITR_MAX_BASEBACKUP_AGE_HOURS}")' in check_step["run"]
    assert "postgres-pitr-check.log" in check_step["run"]
    assert "pitr_required:" in summary_step["run"]
    assert artifact_step["if"] == "always()"
    assert artifact_step["with"]["path"] == "postgres-pitr-check.log"


def test_postgres_pitr_status_uses_activity_aware_remote_wal_gate():
    script = (REPO_ROOT / "scripts/ha/check_postgres_pitr_status.sh").read_text(
        encoding="utf-8"
    )

    assert "is_uploadable_wal_name" in script
    assert '--local-pending-wal-count "${wal_count}"' in script
    assert '--expected-wal "${last_archived_wal}"' in script
    assert "pitr_remote_wal status=idle" in script
    assert "no uploadable WAL is pending locally" in script


def test_postgres_pitr_restore_drill_workflow_preserves_required_gate_and_wal_proof():
    workflow = _workflow(".github/workflows/postgres-pitr-restore-drill.yml")
    env = workflow["env"]
    dispatch_inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    gate_step = _step(workflow, "pitr-restore-drill", "Decide Whether To Run")
    ssh_step = _step(workflow, "pitr-restore-drill", "Setup API SSH Key")
    drill_step = _step(workflow, "pitr-restore-drill", "Run PostgreSQL PITR Restore Drill")
    summary_step = _step(workflow, "pitr-restore-drill", "Write Summary")
    artifact_step = _step(workflow, "pitr-restore-drill", "Upload PITR Restore Drill Log")

    assert "POSTGRES_PITR_REQUIRED" in env["PITR_RESTORE_DRILL_REQUIRED"]
    assert dispatch_inputs["required"]["default"] == "false"
    assert dispatch_inputs["require_wal"]["default"] == "true"
    assert "PITR restore drill skipped because POSTGRES_PITR_REQUIRED is not true." in gate_step["run"]
    assert "postgres-pitr-restore-drill.log" in gate_step["run"]
    assert drill_step["if"] == "steps.gate.outputs.run == 'true'"
    assert "API_STANDBY_HOST" in ssh_step["env"]
    assert 'ssh-keyscan -T 10 -H "${API_STANDBY_HOST}"' in ssh_step["run"]
    assert "API_DB_HA_MODE" in drill_step["env"]
    assert "API_STANDBY_PROJECT_DIR" in drill_step["env"]
    assert "check_patroni_production.py --resolve-primary" in drill_step["run"]
    assert "target_compose_file=docker-compose.patroni.yml" in drill_step["run"]
    assert 'selected_node=${target_label} ha_mode=${API_DB_HA_MODE}' in drill_step["run"]
    assert "scripts/ha/restore_postgres_pitr_drill.sh" in drill_step["run"]
    assert "REQUIRE_WAL=$(quote \"${PITR_RESTORE_REQUIRE_WAL}\")" in drill_step["run"]
    assert "postgres-pitr-restore-drill.log" in drill_step["run"]
    assert "require_wal:" in summary_step["run"]
    assert artifact_step["if"] == "always()"
    assert artifact_step["with"]["path"] == "postgres-pitr-restore-drill.log"
