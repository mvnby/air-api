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
