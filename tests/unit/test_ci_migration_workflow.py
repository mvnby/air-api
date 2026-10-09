from pathlib import Path
import os
import subprocess

import pytest
import yaml


CI_WORKFLOW = Path(".github/workflows/ci.yml")
CI_COMPOSE_OVERRIDE = Path(".github/docker-compose.ci.yml")


def test_ci_verifies_empty_database_migration_and_single_head():
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "Verify Alembic Upgrade From Empty Database" in workflow
    assert "app alembic upgrade head" in workflow
    assert "app alembic check" in workflow
    assert "app alembic heads" in workflow
    assert "SELECT count(*) FROM alembic_version" in workflow


def test_ci_leaves_storefront_checks_to_the_standalone_service():
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "Build Manager Frontend" in workflow
    assert "working-directory: ./web" not in workflow
    assert "Check Storefront" not in workflow


def test_ci_parallelizes_isolated_lanes_behind_required_test_gate():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    assert set(jobs) == {
        "changes",
        "manager-dist",
        "manager",
        "backend-contracts",
        "python-tests",
        "test",
    }
    assert jobs["python-tests"]["strategy"] == {
        "fail-fast": False,
        "matrix": {"suite": ["unit", "integration"]},
    }
    assert jobs["python-tests"]["timeout-minutes"] == "${{ matrix.suite == 'unit' && 75 || 60 }}"
    assert jobs["changes"]["outputs"] == {
        "docs_only": "${{ steps.scope.outputs.docs_only }}",
        "pitr_capacity_proof": "${{ steps.pitr-proof.outputs.run }}",
    }
    assert jobs["changes"]["permissions"]["actions"] == "read"
    scope = next(step for step in jobs["changes"]["steps"] if step.get("id") == "scope")
    assert 'elif [ "$GITHUB_EVENT_NAME" = "push" ]' in scope["run"]
    assert "--verify-previous-push" in scope["run"]
    checkout = jobs["changes"]["steps"][0]
    assert checkout["with"] == {"fetch-depth": 0, "persist-credentials": False}
    assert jobs["manager-dist"]["needs"] == "changes"
    assert jobs["manager"]["needs"] == "changes"
    assert jobs["backend-contracts"]["needs"] == ["changes", "manager-dist"]
    assert jobs["python-tests"]["needs"] == ["changes", "manager-dist"]
    for name in ("manager-dist", "manager", "backend-contracts", "python-tests"):
        assert jobs[name]["if"] == "needs.changes.outputs.docs_only != 'true'"
    assert jobs["test"]["needs"] == [
        "changes",
        "manager-dist",
        "manager",
        "backend-contracts",
        "python-tests",
    ]
    assert jobs["test"]["if"] == "always()"
    assert jobs["test"]["timeout-minutes"] == 5
    gate = jobs["test"]["steps"][0]
    assert gate["env"] == {
        "CHANGES_RESULT": "${{ needs.changes.result }}",
        "DOCS_ONLY": "${{ needs.changes.outputs.docs_only }}",
        "MANAGER_DIST_RESULT": "${{ needs.manager-dist.result }}",
        "MANAGER_RESULT": "${{ needs.manager.result }}",
        "BACKEND_CONTRACTS_RESULT": "${{ needs.backend-contracts.result }}",
        "PYTHON_TESTS_RESULT": "${{ needs.python-tests.result }}",
    }


@pytest.mark.parametrize("docs_only,changes,lane_result,passed", [
    ("true", "success", "skipped", True),
    ("false", "success", "success", True),
    ("false", "success", "skipped", False),
    ("true", "success", "success", False),
    ("true", "failure", "skipped", False),
    ("true", "cancelled", "skipped", False),
    ("", "success", "success", False),
    ("invalid", "success", "success", False),
    ("false", "success", "failure", False),
    ("false", "success", "cancelled", False),
])
def test_required_gate_executes_fail_closed(tmp_path, docs_only, changes, lane_result, passed):
    gate = yaml.safe_load(CI_WORKFLOW.read_text())["jobs"]["test"]["steps"][0]
    env = {**os.environ, **{name: lane_result for name in gate["env"]},
           "CHANGES_RESULT": changes, "DOCS_ONLY": docs_only,
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary")}
    result = subprocess.run(["bash", "-c", gate["run"]], env=env, capture_output=True, text=True)
    assert (result.returncode == 0) is passed, result.stdout + result.stderr


@pytest.mark.parametrize("lane", ["MANAGER_DIST_RESULT", "MANAGER_RESULT", "BACKEND_CONTRACTS_RESULT", "PYTHON_TESTS_RESULT"])
def test_required_gate_rejects_one_failed_lane(tmp_path, lane):
    gate = yaml.safe_load(CI_WORKFLOW.read_text())["jobs"]["test"]["steps"][0]
    env = {**os.environ, **{name: "success" for name in gate["env"]},
           "DOCS_ONLY": "false", lane: "failure",
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary")}
    assert subprocess.run(["bash", "-c", gate["run"]], env=env, capture_output=True).returncode != 0


def test_ci_keeps_full_coverage_with_compact_diagnostic_output():
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "suite: [unit, integration]" in workflow
    assert "pytest -q -n 4 --dist loadscope" in workflow
    assert "--tb=short --durations=25 --durations-min=1.0" in workflow
    assert '"tests/${PYTEST_SUITE}"' in workflow
    assert "EXPECT_XDIST_DATABASE_ISOLATION=1" in workflow
    assert "pytest -q -n 4 --dist load \\" in workflow
    assert "test_postgres_worker_database_isolation.py" in workflow
    assert "--junitxml=/test-results/results.xml" in workflow
    assert "pytest_status=$?" in workflow
    assert "chmod 0644 /test-results/results.xml" in workflow
    assert 'exit "${pytest_status}"' in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "pytest -v" not in workflow


def test_ci_uses_dependency_cache_and_isolated_compose_cleanup():
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    jobs = yaml.safe_load(workflow)["jobs"]

    assert workflow.count("cache-dependency-path: manager_frontend/package-lock.json") == 3
    assert workflow.count("npm run build") == 1
    assert workflow.count("actions/download-artifact@") == 2
    assert workflow.count("manager-dist-${{ github.run_id }}") == 3
    assert "github.run_attempt" not in workflow
    assert workflow.count("docker/setup-buildx-action@") == 2
    assert workflow.count("docker/build-push-action@") == 2
    assert (
        workflow.count("cache-from: type=gha,scope=air-api-ci-backend-v1,timeout=3m")
        == 2
    )
    assert workflow.count("cache-to:") == 1
    assert "github.event.pull_request.head.repo.full_name == github.repository" in workflow
    assert "docker compose up -d --no-build app db_test" in workflow
    assert "docker compose up -d --build" not in workflow
    assert workflow.count("docker compose down -v --remove-orphans") == 2

    expected_image_env = {
        "COMPOSE_FILE": "docker-compose.yml:.github/docker-compose.ci.yml",
        "COMPOSE_PROJECT_NAME": "air-api-ci",
        "CI_APP_IMAGE": "air-api-ci-app:latest",
    }
    assert jobs["backend-contracts"]["env"] == expected_image_env
    assert jobs["python-tests"]["env"] == expected_image_env

    manager_upload = next(
        step
        for step in jobs["manager-dist"]["steps"]
        if step.get("name") == "Upload Manager Frontend Build"
    )
    assert manager_upload["uses"] == (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    )
    assert manager_upload["with"]["retention-days"] == 1
    assert manager_upload["with"]["if-no-files-found"] == "error"
    assert manager_upload["with"]["overwrite"] is True
    manager_steps = "\n".join(
        str(step.get("run", "")) for step in jobs["manager"]["steps"]
    )
    assert "npm run test:components" in manager_steps
    assert "npm run build" not in manager_steps

    backend_build = next(
        step
        for step in jobs["backend-contracts"]["steps"]
        if step.get("name") == "Build Immutable API Image With Remote Cache"
    )
    python_build = next(
        step
        for step in jobs["python-tests"]["steps"]
        if step.get("name") == "Build Immutable Test Image With Remote Cache"
    )
    assert backend_build["with"]["cache-to"].endswith("|| '' }}")
    assert "ignore-error=true" in backend_build["with"]["cache-to"]
    assert "timeout=5m" in backend_build["with"]["cache-to"]
    assert "cache-to" not in python_build["with"]
    assert backend_build["continue-on-error"] is True
    assert python_build["continue-on-error"] is True
    assert backend_build["with"]["load"] is True
    assert python_build["with"]["load"] is True
    assert workflow.count("Remote Docker cache unavailable") == 2
    assert workflow.count('docker build --pull --tag "${CI_APP_IMAGE}" .') == 2

    compose_override = yaml.safe_load(CI_COMPOSE_OVERRIDE.read_text(encoding="utf-8"))
    source_services = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))["services"]
    assert compose_override == {
        "services": {
            "app": {"image": "${CI_APP_IMAGE:?CI_APP_IMAGE must be set for CI}"},
            "db": {"image": f"mirror.gcr.io/library/{source_services['db']['image']}"},
            "db_test": {"image": f"mirror.gcr.io/library/{source_services['db_test']['image']}"},
            "gotenberg": {"image": f"mirror.gcr.io/{source_services['gotenberg']['image']}"},
        }
    }
