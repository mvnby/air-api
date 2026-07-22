from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
MAINTENANCE_AWARE_WORKFLOWS = (
    (".github/workflows/check-postgres-replication.yml", "check"),
    (".github/workflows/check-api-ha-readiness.yml", "audit"),
    (".github/workflows/check-api-vps-health.yml", "check"),
    (".github/workflows/check-api-ha-invariants.yml", "check"),
    (".github/workflows/report-ha-status.yml", "report"),
)


def _workflow(path: str) -> dict:
    return yaml.load(
        (REPO_ROOT / path).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_frequent_ha_workflows_skip_only_after_official_maintenance_proof():
    for path, job_name in MAINTENANCE_AWARE_WORKFLOWS:
        workflow = _workflow(path)
        steps = workflow["jobs"][job_name]["steps"]
        detector = next(
            step for step in steps if step.get("name") == "Detect official Patroni maintenance"
        )
        detector_index = steps.index(detector)
        normal_step = steps[detector_index + 1]

        assert detector["id"] == "maintenance"
        assert "API_DB_HA_MODE" in detector["if"]
        assert "check_patroni_maintenance.py" in detector["run"]
        assert '--github-output "${GITHUB_OUTPUT}"' in detector["run"]
        assert "2>&1 | tee" in detector["run"]
        assert normal_step["if"] == "steps.maintenance.outputs.active != 'true'"
        summaries = [
            step["run"] for step in steps if step.get("name") == "Write Summary"
        ]
        if summaries:
            assert "official_maintenance:" in summaries[0]


def test_scheduled_restore_drills_allow_bounded_maintenance_skip_only_on_schedule():
    for path, job_name, step_name in (
        (
            ".github/workflows/api-restore-drill.yml",
            "restore-drill",
            "Run logical restore drill on the proven Patroni primary",
        ),
        (
            ".github/workflows/postgres-pitr-restore-drill.yml",
            "pitr-restore-drill",
            "Run PostgreSQL PITR Restore Drill",
        ),
    ):
        workflow = _workflow(path)
        step = next(
            item
            for item in workflow["jobs"][job_name]["steps"]
            if item.get("name") == step_name
        )

        assert 'if [ "${GITHUB_EVENT_NAME}" = "schedule" ]' in step["run"]
        assert "args+=(--allow-maintenance-skip)" in step["run"]
