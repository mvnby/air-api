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
    assert "publish_run_id" in workflow["on"]["workflow_dispatch"]["inputs"]
    assert "publish_run_attempt" in workflow["on"]["workflow_dispatch"]["inputs"]
    input_gate = _step(workflow["jobs"]["rollout"], "Require explicit exact production inputs")[
        "run"
    ]
    assert 'GITHUB_REF}" != "refs/heads/main"' in input_gate


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
        },
        {
            "name": "Log in to GHCR for immutable release verification",
            "uses": "docker/login-action@af1e73f918a031802d376d3c8bbc3fe56130a9b0",
            "with": {
                "registry": "ghcr.io",
                "username": "${{ github.actor }}",
                "password": "${{ github.token }}",
            },
        },
        {
            "name": "Set up Docker Buildx for registry evidence",
            "uses": "docker/setup-buildx-action@8d2750c68a42422c14e847fe6c8ac0403b4cbd6f",
        },
    ]
    gate = _step(job, "Require exact tested main SHA and successful CI")["run"]
    assert "git rev-parse origin/main" in gate
    assert "--workflow ci.yml" in gate
    assert 'test "${count}" -ge 1' in gate
    publish = _step(job, "Verify exact successful publish run and evidence artifact")[
        "run"
    ]
    assert "publish-patroni-image.yml" in publish
    assert "/attempts/${PUBLISH_RUN_ATTEMPT}" in publish
    assert "patroni-release-evidence-${PUBLISH_RUN_ID}-${PUBLISH_RUN_ATTEMPT}" in publish
    assert "patroni-manifest.json" in publish
    assert "patroni_rehearsal.log" in publish
    assert "release evidence manifest differs from target digest" in publish
    registry = _step(job, "Verify live SHA tag and registry provenance and SBOM")[
        "run"
    ]
    assert "patroni:${DEPLOY_SHA}" in registry
    assert "verify_patroni_release_image.py" in registry
    attest = _step(job, "Verify exact GitHub SLSA attestation identity")["run"]
    assert "https://slsa.dev/provenance/v1" in attest
    assert "https://spdx.dev/Document" not in attest
    assert "--deny-self-hosted-runners" in attest
    assert "DEPLOY_SHA" in attest
    rollout = _step(job, "Roll out exact Patroni digest standby first")["run"]
    assert "rollout_patroni_image.py" in rollout
    assert "--apply true" in rollout
    assert "--maintenance-transaction-id" in rollout
    assert "--publish-run-id" in rollout
    assert "--publish-run-attempt" in rollout
    workflow_source = WORKFLOW.read_text(encoding="utf-8")
    assert "docker build " not in workflow_source
    assert "docker/build-push-action" not in workflow_source
