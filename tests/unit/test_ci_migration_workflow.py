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


def test_ci_runs_storefront_theme_and_behavior_checks():
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "Check Storefront" in workflow
    assert "npm run audit:theme" in workflow
    assert "npm run test:catalog" in workflow
    assert "npm run test:seo" in workflow


def test_ci_timeout_covers_the_full_immutable_image_suite():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))

    assert workflow["jobs"]["test"]["timeout-minutes"] == 45
