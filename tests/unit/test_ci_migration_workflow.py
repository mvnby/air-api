from pathlib import Path

import yaml


CI_WORKFLOW = Path(".github/workflows/ci.yml")


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

    assert set(jobs) == {"manager", "backend-contracts", "python-tests", "test"}
    assert jobs["python-tests"]["strategy"] == {
        "fail-fast": False,
        "matrix": {"suite": ["unit", "integration"]},
    }
    assert jobs["python-tests"]["timeout-minutes"] == 60
    assert jobs["test"]["needs"] == [
        "manager",
        "backend-contracts",
        "python-tests",
    ]
    assert jobs["test"]["if"] == "always()"
    assert jobs["test"]["timeout-minutes"] == 5


def test_ci_keeps_full_coverage_with_compact_diagnostic_output():
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "suite: [unit, integration]" in workflow
    assert 'pytest -q --tb=short --durations=25 --durations-min=1.0' in workflow
    assert '"tests/${PYTEST_SUITE}"' in workflow
    assert "--junitxml=/test-results/results.xml" in workflow
    assert "pytest_status=$?" in workflow
    assert "chmod 0644 /test-results/results.xml" in workflow
    assert 'exit "${pytest_status}"' in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "pytest -v" not in workflow


def test_ci_uses_dependency_cache_and_isolated_compose_cleanup():
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("cache-dependency-path: manager_frontend/package-lock.json") == 3
    assert "docker compose up -d --build app db_test" in workflow
    assert workflow.count("docker compose down -v --remove-orphans") == 2
