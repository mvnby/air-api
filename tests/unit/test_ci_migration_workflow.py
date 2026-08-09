from pathlib import Path

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
    assert jobs["python-tests"]["timeout-minutes"] == 60
    assert "needs" not in jobs["manager-dist"]
    assert "needs" not in jobs["manager"]
    assert jobs["backend-contracts"]["needs"] == "manager-dist"
    assert jobs["python-tests"]["needs"] == "manager-dist"
    assert jobs["test"]["needs"] == [
        "manager-dist",
        "manager",
        "backend-contracts",
        "python-tests",
    ]
    assert jobs["test"]["if"] == "always()"
    assert jobs["test"]["timeout-minutes"] == 5
    gate = jobs["test"]["steps"][0]
    assert gate["env"] == {
        "MANAGER_DIST_RESULT": "${{ needs.manager-dist.result }}",
        "MANAGER_RESULT": "${{ needs.manager.result }}",
        "BACKEND_CONTRACTS_RESULT": "${{ needs.backend-contracts.result }}",
        "PYTHON_TESTS_RESULT": "${{ needs.python-tests.result }}",
    }
    for result in gate["env"]:
        assert f'test "${{{result}}}" = "success"' in gate["run"]


def test_ci_keeps_full_coverage_with_compact_diagnostic_output():
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "suite: [unit, integration]" in workflow
    assert "pytest -q -n 2 --dist loadscope" in workflow
    assert "--tb=short --durations=25 --durations-min=1.0" in workflow
    assert '"tests/${PYTEST_SUITE}"' in workflow
    assert "EXPECT_XDIST_DATABASE_ISOLATION=1" in workflow
    assert "pytest -q -n 2 --dist load \\" in workflow
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
    assert "manager-dist-${{ github.run_id }}-${{ github.run_attempt }}" in workflow
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
    assert compose_override == {
        "services": {
            "app": {"image": "${CI_APP_IMAGE:?CI_APP_IMAGE must be set for CI}"}
        }
    }
