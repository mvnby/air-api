from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _workflow(path: str) -> dict:
    return yaml.load((REPO_ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(job: dict, step_name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == step_name)


def test_deploy_workflow_checks_active_passive_after_standby_deploy():
    workflow = _workflow(".github/workflows/deploy-api-standby.yml")
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
    expected_environments = {"deploy-backend": "production-api"}

    for job_name, environment in expected_environments.items():
        job = jobs[job_name]
        assert job["environment"] == environment
        checkout = next(
            step
            for step in job["steps"]
            if step.get("uses")
            == "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10"
        )
        assert checkout["with"]["ref"] == "${{ needs.release-gate.outputs.deploy_sha }}"

    standby_workflow = _workflow(".github/workflows/deploy-api-standby.yml")
    standby = standby_workflow["jobs"]["deploy-api-standby"]
    assert standby["environment"] == "standby-api"
    checkout = next(
        step
        for step in standby["steps"]
        if step.get("uses")
        == "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10"
    )
    assert checkout["with"]["ref"] == "${{ inputs.deploy_sha }}"
    standby_call = jobs["deploy-api-standby"]
    assert standby_call["uses"] == "./.github/workflows/deploy-api-standby.yml"
    assert "always()" in standby_call["if"]
    assert "needs.backend-release.result == 'success'" in standby_call["if"]
    assert standby_call["with"]["deploy_sha"] == "${{ needs.release-gate.outputs.deploy_sha }}"
    assert standby_call["with"]["backend_image"] == "${{ needs.backend-release.outputs.backend_image }}"
    assert standby_call["secrets"] == "inherit"

    web_workflow = _workflow(".github/workflows/deploy-web.yml")
    web_job = web_workflow["jobs"]["production-web"]
    assert web_job["environment"] == "production-web"
    web_checkout = next(
        step
        for step in web_job["steps"]
        if step.get("uses")
        == "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10"
    )
    assert web_checkout["with"]["ref"] == "${{ inputs.deploy_sha }}"
    web_call = jobs["deploy-frontend"]
    assert web_call["uses"] == "./.github/workflows/deploy-web.yml"
    assert "always()" in web_call["if"]
    assert "needs.backend-release.result == 'success'" in web_call["if"]
    assert web_call["with"]["deploy_sha"] == "${{ needs.release-gate.outputs.deploy_sha }}"
    assert web_call["secrets"] == "inherit"
    assert "backend-release" in web_call["needs"]

    workflow_text = (REPO_ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    assert "backend:latest" not in workflow_text
    assert "backend:${{ github.sha }}" not in workflow_text
    assert "backend:${GITHUB_SHA}" not in workflow_text
    assert "tags: ghcr.io/${{ steps.prep.outputs.repo }}/backend:${{ needs.release-gate.outputs.deploy_sha }}" in workflow_text
    assert "BACKEND_IMAGE=${{ steps.resolve_backend_image.outputs.reference }}" in workflow_text
    assert 'reference="ghcr.io/${{ steps.prep.outputs.repo }}/backend@${digest}"' in workflow_text


def test_frontend_detection_compares_against_the_deployed_release_sha():
    workflow = _workflow(".github/workflows/deploy.yml")
    detect = _step(workflow["jobs"]["detect-frontend-changes"], "Detect storefront-relevant changes")[
        "run"
    ]

    assert "https://mvn.by/release.json?ci_run=${GITHUB_RUN_ID}" in detect
    assert 'git merge-base --is-ancestor "${deployed_web_sha}" "${after}"' in detect
    assert 'git diff --name-only "${deployed_web_sha}" "${after}"' in detect
    assert "deploying frontend conservatively" in detect


def test_backend_release_is_scoped_and_has_guarded_rollback():
    workflow = _workflow(".github/workflows/deploy.yml")
    standby_workflow = _workflow(".github/workflows/deploy-api-standby.yml")
    jobs = workflow["jobs"]
    backend = jobs["deploy-backend"]
    standby = standby_workflow["jobs"]["deploy-api-standby"]
    rollback = _step(backend, "Roll Back Backend After Failed Activation")
    primary_copy = _step(backend, "Copy Compose Files and Scripts to Server")
    primary_deploy = _step(backend, "Execute Deployment Script")
    primary_smoke = _step(backend, "Post-Deploy Smoke Check")
    standby_deploy = _step(standby, "Deploy standby API app image")
    standby_rollback = _step(standby, "Roll Back Standby After Failed Activation")
    primary_prune = _step(backend, "Prune Unused Backend Docker Images")
    standby_prune = _step(standby, "Prune Unused Standby Docker Images")

    assert "steps.deploy_backend.outcome == 'failure'" in rollback["if"]
    assert "steps.post_deploy_smoke.outcome" not in rollback["if"]
    assert "EXPECTED_CURRENT_IMAGE=" in rollback["run"]
    assert "API_FORCE_COMPOSE_RECONCILE_ON_NOOP=true" in rollback["run"]
    assert "scripts/rollback_backend.sh" in rollback["run"]
    assert '.candidate-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}' in primary_copy["run"]
    assert "scp \\" in primary_copy["run"]
    assert "scripts/ha/run_verified_remote_bundle.py" in primary_deploy["run"]
    assert "deploy_backend_blue_green.sh" in primary_deploy["run"]
    assert "deploy_backend_blue_green_safety.sh" in primary_deploy["run"]
    assert "scripts/ha/require_deploy_capacity.sh" in primary_deploy["run"]
    assert "compose_candidate_transaction.sh" in primary_deploy["run"]
    assert "reconcile_backend_compose_runtime.sh" in primary_deploy["run"]
    assert "deploy_backend_candidate_transaction.sh" in primary_deploy["run"]
    assert "API_CANONICAL_COMPOSE_FILE=" in primary_deploy["run"]
    assert "API_CANDIDATE_COMPOSE_FILE=" in primary_deploy["run"]
    assert "API_COMPOSE_TRANSACTIONAL=" in primary_deploy["run"]
    assert "API_SMOKE_SCRIPT=__MVN_BUNDLE__/post_deploy_smoke_check.sh" in primary_deploy["run"]
    assert "--entry deploy_backend_candidate_transaction.sh" in primary_deploy["run"]
    assert '--env "API_RUN_MIGRATIONS=${API_RUN_MIGRATIONS}"' in primary_deploy["run"]
    assert "smoke_status=passed" in primary_smoke["run"]
    assert "compose promotion completed" in primary_smoke["run"]
    assert "scripts/deploy_backend_blue_green.sh" in rollback["run"]
    assert "scripts/deploy_backend_blue_green_safety.sh" in rollback["run"]
    safety_helper_env = (
        "API_BLUE_GREEN_SAFETY_HELPER=__MVN_BUNDLE__/deploy_backend_blue_green_safety.sh"
    )
    assert safety_helper_env in primary_deploy["run"]
    assert safety_helper_env in rollback["run"]
    capacity_helper_env = (
        "API_DEPLOY_CAPACITY_HELPER=__MVN_BUNDLE__/require_deploy_capacity.sh"
    )
    assert capacity_helper_env in primary_deploy["run"]
    assert capacity_helper_env in rollback["run"]
    assert "scripts/ha/require_deploy_capacity.sh" in rollback["run"]
    assert "scripts/deploy.sh" in standby_deploy["run"]
    assert '.candidate-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}' in standby_deploy["run"]
    assert "scripts/deploy_backend_candidate_transaction.sh" in standby_deploy["run"]
    assert '--env "API_COMPOSE_TRANSACTIONAL=${API_STANDBY_COPY_COMPOSE}"' in standby_deploy["run"]
    assert "API_SMOKE_SCRIPT=__MVN_BUNDLE__/post_deploy_smoke_check.sh" in standby_deploy["run"]
    assert "--entry deploy_backend_candidate_transaction.sh" in standby_deploy["run"]
    assert "--env API_DEPLOY_SERVICES=app" in standby_deploy["run"]
    assert "scripts/ha/safe_deploy_lock.py" in standby_deploy["run"]
    assert "API_DEPLOY_LOCK_HELPER=__MVN_BUNDLE__/safe_deploy_lock.py" in standby_deploy["run"]
    assert '--env "API_DEPLOY_LOCK_HELPER_SHA256=${lock_helper_sha256}"' in standby_deploy["run"]
    assert '--env "API_ACTIVE_SLOT_FILE=${API_STANDBY_PROJECT_DIR}/.standby-api-slot-disabled"' in standby_deploy["run"]
    assert "--env API_RUN_MIGRATIONS=false" in standby_deploy["run"]
    assert "steps.deploy_standby.outcome == 'failure'" in standby_rollback["if"]
    assert "--env API_DEPLOY_SERVICES=app" in standby_rollback["run"]
    assert '--env "API_ACTIVE_SLOT_FILE=${API_STANDBY_PROJECT_DIR}/.standby-api-slot-disabled"' in standby_rollback["run"]
    assert "API_FORCE_COMPOSE_RECONCILE_ON_NOOP=true" in standby_rollback["run"]
    assert "scripts/ha/safe_deploy_lock.py" in standby_rollback["run"]
    assert "API_DEPLOY_LOCK_HELPER=__MVN_BUNDLE__/safe_deploy_lock.py" in standby_rollback["run"]
    assert '--env "API_DEPLOY_LOCK_HELPER_SHA256=${lock_helper_sha256}"' in standby_rollback["run"]
    assert "scripts/ha/safe_deploy_lock.py" in rollback["run"]
    assert "API_DEPLOY_LOCK_HELPER=__MVN_BUNDLE__/safe_deploy_lock.py" in rollback["run"]
    assert '--env "API_DEPLOY_LOCK_HELPER_SHA256=${lock_helper_sha256}"' in rollback["run"]
    assert primary_prune["continue-on-error"] == "true"
    assert standby_prune["continue-on-error"] == "true"
    workflow_text = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in (".github/workflows/deploy.yml", ".github/workflows/deploy-api-standby.yml")
    )
    assert "GHCR_PAT='${{ secrets.GHCR_PAT }}'" not in workflow_text
    assert "--secret-env GHCR_PAT" in workflow_text
    assert ".rollback-candidate" not in workflow_text
    assert "cat > /tmp/" not in workflow_text
    assert "/tmp/safe_deploy_lock.py" not in workflow_text
    assert "/tmp/backend_blue_green_summary" not in workflow_text
    for step in (primary_deploy, rollback, standby_deploy, standby_rollback):
        assert "cat > /tmp/" not in step["run"]
        assert "/tmp/safe_deploy_lock.py" not in step["run"]
        assert "run_verified_remote_bundle.py" in step["run"]


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


def test_production_compose_has_private_profiled_api_slots():
    for path in (
        "docker-compose.prod.yml",
        "deploy/ha/mvn-api/docker-compose.primary.yml",
    ):
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert "app-blue:" in text
        assert "app-green:" in text
        assert text.count("profiles: [bluegreen]") == 2
        assert '"127.0.0.1:18001:8000"' in text
        assert '"127.0.0.1:18002:8000"' in text
