from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/recover-patroni-preflight-incident.yml"


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(job, name):
    return next(step for step in job["steps"] if step.get("name") == name)


def test_recovery_workflow_is_manual_approved_serialized_and_current_main_only():
    workflow = _workflow()
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["concurrency"] == {
        "group": "production-release",
        "cancel-in-progress": "false",
    }
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    job = workflow["jobs"]["recover"]
    assert job["environment"] == "production-api"
    assert job["timeout-minutes"] == "20"
    gate = _step(job, "Require exact current main recovery SHA")["run"]
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in gate
    assert 'test "${APPLY}" = "true"' in gate
    ci = _step(job, "Require current main SHA and successful CI")["run"]
    assert 'git rev-parse origin/main' in ci
    assert "--workflow ci.yml" in ci
    assert 'test "${count}" -ge 1' in ci


def test_recovery_workflow_pins_checkout_and_invokes_only_reviewed_recovery():
    workflow = _workflow()
    job = workflow["jobs"]["recover"]
    action_steps = [step for step in job["steps"] if "uses" in step]
    assert action_steps == [
        {
            "name": "Checkout exact tested recovery SHA",
            "uses": "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10",
            "with": {
                "fetch-depth": "0",
                "persist-credentials": "false",
                "ref": "${{ inputs.deploy_sha }}",
            },
        }
    ]
    recovery = _step(
        job, "Terminalize exact preflight journals and remove only cutover markers"
    )["run"]
    assert "recover_patroni_preflight_incident.py" in recovery
    assert "--apply true" in recovery
    source = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in (
        "docker compose up",
        "docker pull",
        "patronictl edit-config",
        "pg_switch_wal",
        "systemctl start",
        "systemctl enable",
    ):
        assert forbidden not in source
    summary = _step(job, "Record immutable recovery result")["run"]
    assert "PITR_maintenance_fence: retained" in summary


def test_recovery_workflow_retries_public_readiness_and_reports_final_body():
    workflow = _workflow()
    readiness = _step(
        workflow["jobs"]["recover"], "Prove public API remained ready"
    )["run"]

    assert "for attempt in $(seq 1 12)" in readiness
    assert 'if test "${attempt}" -lt 12' in readiness
    assert "sleep 5" in readiness
    assert 'test "${code}" = "200"' in readiness
    assert '.api == "ready" and .traffic == "enabled"' in readiness
    assert 'test "${ready}" != "true"' in readiness
    assert "after 12 attempts" in readiness
    assert 'cat "${ready_file}"' in readiness
