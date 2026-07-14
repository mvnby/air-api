from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/rollout-patroni-image.yml"


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(job, name):
    return next(step for step in job["steps"] if step.get("name") == name)


def test_rollout_workflow_is_manual_reusable_approved_and_serialized():
    workflow = _workflow()
    assert {"workflow_dispatch", "workflow_call"} <= set(workflow["on"])
    assert workflow["concurrency"] == {
        "group": "production-release",
        "cancel-in-progress": "false",
    }
    job = workflow["jobs"]["rollout"]
    assert job["environment"] == "production-api"
    assert workflow["permissions"]["contents"] == "read"
    assert workflow["permissions"]["packages"] == "read"
    assert workflow["permissions"]["attestations"] == "read"
    assert "maintenance_transaction_id" in workflow["on"]["workflow_dispatch"]["inputs"]


def test_rollout_workflow_pins_actions_and_gates_exact_main_ci_attestations():
    workflow = _workflow()
    job = workflow["jobs"]["rollout"]
    action_steps = [step for step in job["steps"] if "uses" in step]
    assert action_steps == [
        {
            "name": "Checkout exact tested SHA",
            "uses": "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10",
            "with": {
                "fetch-depth": "0",
                "persist-credentials": "false",
                "ref": "${{ inputs.deploy_sha }}",
            },
        }
    ]
    gate = _step(job, "Require exact tested main SHA and successful CI")["run"]
    assert "git rev-parse origin/main" in gate
    assert "--workflow ci.yml" in gate
    assert 'test "${count}" -ge 1' in gate
    attest = _step(job, "Verify target provenance and SBOM attestations")["run"]
    assert "https://slsa.dev/provenance/v1" in attest
    assert "https://spdx.dev/Document" in attest
    assert "DEPLOY_SHA" in attest
    rollout = _step(job, "Roll out exact Patroni digest standby first")["run"]
    assert "rollout_patroni_image.py" in rollout
    assert "--apply true" in rollout
    assert "--maintenance-transaction-id" in rollout
    assert "docker build" not in WORKFLOW.read_text(encoding="utf-8")
