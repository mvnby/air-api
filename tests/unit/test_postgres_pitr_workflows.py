from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKOUT_SHA = "df4cb1c069e1874edd31b4311f1884172cec0e10"


def _workflow(path: str) -> dict:
    return yaml.load((REPO_ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(workflow: dict, job_name: str, step_name: str) -> dict:
    steps = workflow["jobs"][job_name]["steps"]
    return next(step for step in steps if step.get("name") == step_name)


def test_postgres_pitr_check_workflow_preserves_strict_remote_gate():
    workflow = _workflow(".github/workflows/check-postgres-pitr.yml")
    checkout_step = _step(workflow, "check", "Checkout")
    dispatch_inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    gate_step = _step(workflow, "check", "Decide Whether To Run")
    check_step = _step(workflow, "check", "Run PostgreSQL PITR Check")
    summary_step = _step(workflow, "check", "Write Summary")
    artifact_step = _step(workflow, "check", "Upload PITR Check Log")

    assert dispatch_inputs == {"required": dispatch_inputs["required"]}
    assert checkout_step["uses"] == f"actions/checkout@{CHECKOUT_SHA}"
    assert checkout_step["with"] == {
        "ref": "${{ github.sha }}",
        "persist-credentials": "false",
    }
    assert dispatch_inputs["required"]["default"] == "true"
    assert "POSTGRES_PITR_REQUIRED" in workflow["env"]["PITR_CHECK_REQUIRED"]
    assert "must be exactly true or false" in gate_step["run"]
    assert check_step["if"] == "steps.gate.outputs.run == 'true'"
    assert check_step["env"] == {"SSH_KEY": "${{ secrets.SSH_KEY }}"}
    assert "python3 -I scripts/ha/run_postgres_pitr_workflow.py --phase verify" in check_step["run"]
    assert "scripts/ha/check_postgres_pitr_status.sh" not in check_step["run"]
    assert "unset SSH_KEY" in check_step["run"]
    assert "postgres-pitr-check.log" in check_step["run"]
    assert "strict_required:" in summary_step["run"]
    assert "installed strict runner" in summary_step["run"]
    assert artifact_step["if"] == "always()"
    assert artifact_step["with"]["path"] == "postgres-pitr-check.log"

    source = (REPO_ROOT / ".github/workflows/check-postgres-pitr.yml").read_text()
    for forbidden in ("ssh-keyscan", "accept-new", "check_patroni_production.py", "cat >", "/tmp/mvn-"):
        assert forbidden not in source


def test_postgres_pitr_status_uses_activity_aware_remote_wal_gate():
    script = (REPO_ROOT / "scripts/ha/check_postgres_pitr_status.sh").read_text(
        encoding="utf-8"
    )

    assert "is_uploadable_wal_name" in script
    assert '--local-pending-wal-count "${wal_count}"' in script
    assert "SELECT pg_walfile_name(pg_switch_wal())" in script
    assert "pg_create_restore_point" in script
    assert 'WAL_SEGMENT_BYTES="16777216"' in script
    assert '--phase wal-upload' in script
    assert '"action": "uploaded_wal"' in script
    assert '--expected-wal "${forced_wal}"' in script
    assert '--expected-system-identifier "${system_identifier}"' in script
    assert "SELECT system_identifier FROM pg_control_system()" in script
    assert "SELECT setting FROM pg_settings" in script
    assert "EXPECTED_ARCHIVE_TIMEOUT=\"300\"" in script
    assert (
        "EXPECTED_ARCHIVE_COMMAND='/usr/local/bin/mvn-patroni-archive-wal "
        '\"%p\" \"%f\"\''
    ) in script
    assert "pitr_remote_wal status=idle" in script
    assert "no uploadable WAL is pending locally" in script


def test_postgres_pitr_restore_drill_workflow_preserves_required_gate_and_wal_proof():
    workflow = _workflow(".github/workflows/postgres-pitr-restore-drill.yml")
    checkout_step = _step(workflow, "pitr-restore-drill", "Checkout")
    env = workflow["env"]
    dispatch_inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    gate_step = _step(workflow, "pitr-restore-drill", "Decide Whether To Run")
    drill_step = _step(workflow, "pitr-restore-drill", "Run PostgreSQL PITR Restore Drill")
    summary_step = _step(workflow, "pitr-restore-drill", "Write Summary")
    artifact_step = _step(workflow, "pitr-restore-drill", "Upload PITR Restore Drill Log")

    assert "POSTGRES_PITR_REQUIRED" in env["PITR_RESTORE_DRILL_REQUIRED"]
    assert checkout_step["uses"] == f"actions/checkout@{CHECKOUT_SHA}"
    assert checkout_step["with"] == {
        "ref": "${{ github.sha }}",
        "persist-credentials": "false",
    }
    assert dispatch_inputs["required"]["default"] == "true"
    assert dispatch_inputs["require_wal"]["default"] == "true"
    assert "PITR restore drill skipped because POSTGRES_PITR_REQUIRED is false." in gate_step["run"]
    assert "cannot disable the WAL-chain proof" in gate_step["run"]
    assert "postgres-pitr-restore-drill.log" in gate_step["run"]
    assert drill_step["if"] == "steps.gate.outputs.run == 'true'"
    assert drill_step["env"] == {"SSH_KEY": "${{ secrets.SSH_KEY }}"}
    assert "python3 -I scripts/ha/run_postgres_pitr_workflow.py" in drill_step["run"]
    assert "--phase restore-drill" in drill_step["run"]
    assert "--backup-id" in drill_step["run"]
    assert "--target-time" in drill_step["run"]
    assert "scripts/ha/restore_postgres_pitr_drill.sh" not in drill_step["run"]
    assert "unset SSH_KEY" in drill_step["run"]
    assert "postgres-pitr-restore-drill.log" in drill_step["run"]
    assert "require_wal:" in summary_step["run"]
    assert artifact_step["if"] == "always()"
    assert artifact_step["with"]["path"] == "postgres-pitr-restore-drill.log"

    source = (REPO_ROOT / ".github/workflows/postgres-pitr-restore-drill.yml").read_text()
    for forbidden in ("ssh-keyscan", "accept-new", "check_patroni_production.py", "cat >", "/tmp/mvn-"):
        assert forbidden not in source


def test_postgres_pitr_restore_drill_requires_restored_business_data():
    script = (REPO_ROOT / "scripts/ha/restore_postgres_pitr_drill.sh").read_text(
        encoding="utf-8"
    )

    assert "business_counts=" in script
    assert "product_count payment_count order_count" in script
    assert 'log "product_count=${product_count} payment_count=${payment_count} order_count=${order_count}"' in script
    assert '"${product_count}" -lt 1 || "${order_count}" -lt 1' in script
