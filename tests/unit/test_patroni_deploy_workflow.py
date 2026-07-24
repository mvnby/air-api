from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _workflow(path: str) -> dict:
    return yaml.load((REPO_ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(job: dict, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_main_release_selects_exactly_one_physical_or_patroni_path():
    jobs = _workflow(".github/workflows/deploy.yml")["jobs"]

    assert jobs["deploy-backend"]["if"] == "${{ vars.API_DB_HA_MODE != 'patroni' }}"
    patroni = jobs["deploy-backend-patroni"]
    assert patroni["if"] == "${{ vars.API_DB_HA_MODE == 'patroni' }}"
    assert patroni["uses"] == "./.github/workflows/deploy-api-patroni.yml"
    assert patroni["with"]["deploy_sha"] == "${{ needs.release-gate.outputs.deploy_sha }}"
    gate = jobs["backend-release"]
    gate_run = _step(gate, "Require exactly one backend deployment path")["run"]
    assert {"release-gate", "deploy-backend", "deploy-backend-patroni"} == set(gate["needs"])
    assert "physical=${PHYSICAL_RESULT} patroni=${PATRONI_RESULT}" in gate_run
    assert "@sha256:[0-9a-f]{64}" in gate_run
    assert "needs.backend-release.outputs.mode == 'physical'" in jobs["deploy-api-standby"]["if"]


def test_patroni_workflow_builds_exact_sha_and_validates_single_primary():
    workflow = _workflow(".github/workflows/deploy-api-patroni.yml")
    jobs = workflow["jobs"]
    build = jobs["build-backend"]
    checkout = _step(build, "Checkout exact tested SHA")
    image = _step(build, "Resolve immutable backend image")["run"]

    assert checkout["with"]["ref"] == "${{ inputs.deploy_sha }}"
    assert "backend@${digest}" in image
    assert workflow["on"]["workflow_call"]["outputs"]["backend_image"]["value"] == (
        "${{ jobs.build-backend.outputs.backend_image }}"
    )
    topology = _step(jobs["validate-topology"], "Require exactly one Patroni primary")["run"]
    assert "api=${API_ROLE} reserve=${RESERVE_ROLE}" in topology
    assert "primary_node=api" in topology
    assert "primary_node=reserve" in topology


def test_patroni_release_orders_migration_replica_then_primary():
    jobs = _workflow(".github/workflows/deploy-api-patroni.yml")["jobs"]

    assert jobs["migrate-api-node"]["environment"] == "production-api"
    assert jobs["migrate-reserve-node"]["environment"] == "standby-api"
    assert "migrate-api-node" in jobs["deploy-replica-reserve"]["needs"]
    assert "deploy-replica-reserve" in jobs["deploy-primary-api"]["needs"]
    assert "migrate-reserve-node" in jobs["deploy-replica-api"]["needs"]
    assert "deploy-replica-api" in jobs["deploy-primary-reserve"]["needs"]

    for job_name in (
        "migrate-api-node",
        "migrate-reserve-node",
        "deploy-replica-reserve",
        "deploy-replica-api",
        "deploy-primary-api",
        "deploy-primary-reserve",
    ):
        run = jobs[job_name]["steps"][-1]["run"]
        assert "scripts/ha/run_patroni_node_remote.sh" in run
        env = jobs[job_name]["steps"][-1]["env"]
        assert env["BOT_VOICE_TRANSCRIPTION_API_KEY"] == (
            "${{ secrets.BOT_VOICE_TRANSCRIPTION_API_KEY }}"
        )

    text = (REPO_ROOT / ".github/workflows/deploy-api-patroni.yml").read_text(encoding="utf-8")
    assert "up -d db" not in text
    assert "docker compose" not in text


def test_patroni_release_keeps_physical_node_identity_across_role_switches():
    jobs = _workflow(".github/workflows/deploy-api-patroni.yml")["jobs"]
    api_jobs = (
        "probe-api-node",
        "migrate-api-node",
        "deploy-replica-api",
        "deploy-primary-api",
    )
    reserve_jobs = (
        "probe-reserve-node",
        "migrate-reserve-node",
        "deploy-replica-reserve",
        "deploy-primary-reserve",
    )

    for job_name in api_jobs:
        env = jobs[job_name]["steps"][-1]["env"]
        assert "PATRONI_MVN_API_HOST" in env["API_NODE_HOST"]
    for job_name in reserve_jobs:
        env = jobs[job_name]["steps"][-1]["env"]
        assert "PATRONI_ZAKUP_HOST" in env["API_NODE_HOST"]


def test_patroni_deployment_completion_rejects_both_or_neither_branch():
    jobs = _workflow(".github/workflows/deploy-api-patroni.yml")["jobs"]
    complete = jobs["deployment-complete"]
    run = _step(complete, "Require the selected primary branch to succeed")["run"]

    assert complete["if"] == "${{ always() }}"
    assert "test \"${API_RESULT}\" = \"success\"" in run
    assert "test \"${RESERVE_RESULT}\" = \"success\"" in run
    assert "No validated Patroni primary branch completed" in run
