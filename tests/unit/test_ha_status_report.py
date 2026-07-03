import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/ha/report_ha_status.py"
SPEC = importlib.util.spec_from_file_location("report_ha_status", MODULE_PATH)
report_ha_status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = report_ha_status
SPEC.loader.exec_module(report_ha_status)


def _run(name: str, *, created_at: str = "2026-07-03T07:00:00Z", conclusion: str = "success") -> dict:
    return {
        "workflowName": name,
        "displayTitle": name,
        "status": "completed",
        "conclusion": conclusion,
        "createdAt": created_at,
        "url": f"https://github.test/{name}",
    }


def test_evaluate_workflows_passes_fresh_successes():
    now = datetime(2026, 7, 3, 7, 30, tzinfo=timezone.utc)
    latest = {
        "Media CDN Check": report_ha_status.parse_workflow_run(_run("Media CDN Check")),
        "PostgreSQL Replication Check": report_ha_status.parse_workflow_run(_run("PostgreSQL Replication Check")),
    }

    result = report_ha_status.evaluate_workflows(
        latest,
        expected=(
            report_ha_status.ExpectedWorkflow("Media CDN Check", max_age_hours=8),
            report_ha_status.ExpectedWorkflow("PostgreSQL Replication Check", max_age_hours=8),
        ),
        now=now,
    )

    assert result.status == "passed"
    assert len(result.ok) == 2
    assert not result.warnings
    assert not result.failures


def test_evaluate_workflows_flags_missing_failed_and_stale_runs():
    now = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    latest = {
        "Media CDN Check": report_ha_status.parse_workflow_run(
            _run("Media CDN Check", created_at="2026-07-03T01:00:00Z")
        ),
        "PostgreSQL Replication Check": report_ha_status.parse_workflow_run(
            _run("PostgreSQL Replication Check", conclusion="failure")
        ),
    }

    result = report_ha_status.evaluate_workflows(
        latest,
        expected=(
            report_ha_status.ExpectedWorkflow("Media CDN Check", max_age_hours=8),
            report_ha_status.ExpectedWorkflow("PostgreSQL Replication Check", max_age_hours=8),
            report_ha_status.ExpectedWorkflow("API HA Invariant Check", max_age_hours=2),
        ),
        now=now,
    )

    assert result.status == "failed"
    assert any("Media CDN Check: latest success is stale" in warning for warning in result.warnings)
    assert any("PostgreSQL Replication Check: latest run concluded failure" in failure for failure in result.failures)
    assert any("workflow missing from recent run list: API HA Invariant Check" in warning for warning in result.warnings)


def test_external_prereq_failures_are_blockers_until_require_strict(monkeypatch):
    def fake_load_metadata(repo: str):
        assert repo == "mvnby/air-api"
        return object()

    def fake_check_metadata(metadata: object, *, require_strict: bool):
        return ["var present"], ["optional missing"], ["missing cloudflare token"]

    monkeypatch.setattr(report_ha_status, "load_github_metadata", fake_load_metadata)
    monkeypatch.setattr(report_ha_status, "check_metadata", fake_check_metadata)

    soft = report_ha_status.external_prereq_result(repo="mvnby/air-api", require_strict=False)
    strict = report_ha_status.external_prereq_result(repo="mvnby/air-api", require_strict=True)

    assert soft.status == "attention"
    assert soft.blockers == ["missing cloudflare token"]
    assert not soft.failures
    assert strict.status == "failed"
    assert strict.failures == ["missing cloudflare token"]


def test_run_live_active_passive_maps_exit_codes():
    def ok_runner(args, stdin):
        return report_ha_status.subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    def fail_runner(args, stdin):
        return report_ha_status.subprocess.CompletedProcess(args, 1, stdout="", stderr="split brain")

    ok = report_ha_status.run_live_active_passive(
        primary_origin="185.250.45.54",
        standby_origin="193.47.42.213",
        runner=ok_runner,
    )
    failed = report_ha_status.run_live_active_passive(
        primary_origin="185.250.45.54",
        standby_origin="193.47.42.213",
        runner=fail_runner,
    )

    assert ok.status == "passed"
    assert failed.status == "failed"
    assert "active/passive direct-origin invariant failed" in failed.failures[0]
