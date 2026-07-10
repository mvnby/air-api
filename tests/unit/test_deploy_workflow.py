from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _workflow(path: str) -> dict:
    return yaml.load((REPO_ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(job: dict, step_name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == step_name)


def test_deploy_workflow_checks_active_passive_after_standby_deploy():
    workflow = _workflow(".github/workflows/deploy.yml")
    standby_job = workflow["jobs"]["deploy-api-standby"]
    step_names = [step.get("name") for step in standby_job["steps"]]
    invariant_step = _step(standby_job, "Post-Standby Active-Passive Invariant Check")
    artifact_step = _step(standby_job, "Upload Standby Deploy Logs")
    summary_step = _step(standby_job, "Standby Deploy Summary")

    assert standby_job["env"]["API_PRIMARY_ORIGIN"] == "${{ vars.API_PRIMARY_ORIGIN || '185.250.45.54' }}"
    assert standby_job["env"]["API_STANDBY_ORIGIN"] == "${{ vars.API_STANDBY_ORIGIN || '193.47.42.213' }}"
    assert step_names.index("Deploy standby API app image") < step_names.index(
        "Post-Standby Active-Passive Invariant Check"
    )
    assert step_names.index("Post-Standby Active-Passive Invariant Check") < step_names.index(
        "Prune Unused Standby Docker Images"
    )
    assert invariant_step["id"] == "standby_active_passive"
    assert "CHECK_PUBLIC_READY=false" in invariant_step["run"]
    assert 'PRIMARY_ORIGIN="${API_PRIMARY_ORIGIN}"' in invariant_step["run"]
    assert 'STANDBY_ORIGIN="${API_STANDBY_ORIGIN}"' in invariant_step["run"]
    assert "scripts/ha/check_active_passive.sh" in invariant_step["run"]
    assert "standby_active_passive.log" in invariant_step["run"]
    assert "standby_active_passive.log" in artifact_step["with"]["path"]
    assert "active_passive_status:" in summary_step["run"]
    assert "active_passive_log: collected" in summary_step["run"]


def test_deploy_runs_only_after_successful_ci_for_the_exact_sha():
    workflow = _workflow(".github/workflows/deploy.yml")
    trigger = workflow["on"]
    release_gate = workflow["jobs"]["release-gate"]

    assert "push" not in trigger
    assert trigger["workflow_run"]["workflows"] == ["CI (Test & Lint)"]
    assert trigger["workflow_run"]["branches"] == ["main"]
    assert trigger["workflow_run"]["types"] == ["completed"]
    assert workflow["concurrency"] == {
        "group": "production-release",
        "cancel-in-progress": "false",
    }
    assert "github.event.workflow_run.conclusion == 'success'" in release_gate["if"]
    resolve = _step(release_gate, "Resolve tested release SHA")["run"]
    assert 'deploy_sha="${{ github.event.workflow_run.head_sha }}"' in resolve
    assert "No successful CI run found" in resolve


def test_release_jobs_use_immutable_tested_sha_and_protected_environments():
    workflow = _workflow(".github/workflows/deploy.yml")
    jobs = workflow["jobs"]
    expected_environments = {
        "deploy-backend": "production-api",
        "deploy-api-standby": "standby-api",
        "deploy-frontend": "production-web",
    }

    for job_name, environment in expected_environments.items():
        job = jobs[job_name]
        assert job["environment"] == environment
        checkout = next(step for step in job["steps"] if step.get("uses") == "actions/checkout@v6")
        assert checkout["with"]["ref"] == "${{ needs.release-gate.outputs.deploy_sha }}"

    workflow_text = (REPO_ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    assert "backend:latest" not in workflow_text
    assert "backend:${{ github.sha }}" not in workflow_text
    assert "backend:${GITHUB_SHA}" not in workflow_text
    assert "tags: ghcr.io/${{ steps.prep.outputs.repo }}/backend:${{ needs.release-gate.outputs.deploy_sha }}" in workflow_text
    assert "BACKEND_IMAGE='${{ steps.resolve_backend_image.outputs.reference }}'" in workflow_text
    assert 'BACKEND_IMAGE="${{ needs.deploy-backend.outputs.backend_image }}"' in workflow_text
    assert 'reference="ghcr.io/${{ steps.prep.outputs.repo }}/backend@${digest}"' in workflow_text


def test_backend_release_is_scoped_and_has_guarded_rollback():
    workflow = _workflow(".github/workflows/deploy.yml")
    jobs = workflow["jobs"]
    backend = jobs["deploy-backend"]
    standby = jobs["deploy-api-standby"]
    rollback = _step(backend, "Roll Back Backend After Failed Activation")
    standby_deploy = _step(standby, "Deploy standby API app image")
    standby_rollback = _step(standby, "Roll Back Standby After Failed Activation")
    primary_prune = _step(backend, "Prune Unused Backend Docker Images")
    standby_prune = _step(standby, "Prune Unused Standby Docker Images")

    assert "steps.deploy_backend.outcome == 'failure'" in rollback["if"]
    assert "steps.post_deploy_smoke.outcome == 'failure'" in rollback["if"]
    assert "EXPECTED_CURRENT_IMAGE=" in rollback["run"]
    assert "scripts/rollback_backend.sh" in rollback["run"]
    assert "scripts/deploy.sh" in standby_deploy["run"]
    assert "API_DEPLOY_SERVICES='app'" in standby_deploy["run"]
    assert "API_RUN_MIGRATIONS='false'" in standby_deploy["run"]
    assert "steps.deploy_standby.outcome == 'failure'" in standby_rollback["if"]
    assert "API_DEPLOY_SERVICES='app'" in standby_rollback["run"]
    assert primary_prune["continue-on-error"] == "true"
    assert standby_prune["continue-on-error"] == "true"


def test_production_compose_requires_backend_release_and_pins_postgres_digest():
    compose_paths = [
        "docker-compose.prod.yml",
        "deploy/ha/mvn-api/docker-compose.primary.yml",
        "deploy/ha/mvn-api/docker-compose.standby.yml",
        "deploy/ha/zakup/docker-compose.primary.yml",
        "deploy/ha/zakup/docker-compose.standby.yml",
    ]

    for path in compose_paths:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert "backend:latest" not in text
        assert "${BACKEND_IMAGE:?set immutable BACKEND_IMAGE in .env}" in text
        assert "postgres:15.18-alpine@sha256:" in text
