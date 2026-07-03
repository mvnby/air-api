import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _workflow(path: str) -> dict:
    return yaml.load((REPO_ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(workflow: dict, step_name: str) -> dict:
    return next(step for step in workflow["jobs"]["audit"]["steps"] if step.get("name") == step_name)


def test_ha_readiness_script_has_valid_bash_syntax():
    script = REPO_ROOT / "scripts/ha/check_api_ha_readiness.sh"

    result = subprocess.run(["bash", "-n", str(script)], text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr


def test_ha_readiness_workflow_wires_core_and_soft_blocker_inputs():
    workflow = _workflow(".github/workflows/check-api-ha-readiness.yml")
    dispatch_inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    ssh_step = _step(workflow, "Setup API SSH Key")
    audit_step = _step(workflow, "Run API HA readiness audit")
    summary_step = _step(workflow, "Write Summary")
    artifact_step = _step(workflow, "Upload HA readiness log")

    assert dispatch_inputs["strict"]["default"] == "false"
    assert "API_HA_READINESS_STRICT" in workflow["env"]["HA_READINESS_STRICT"]
    assert "secrets.SSH_HOST_API" in ssh_step["env"]["SSH_HOST_API"]
    assert "secrets.SSH_KEY" in ssh_step["env"]["SSH_KEY"]
    assert "CLOUDFLARE_LB_READ_TOKEN" in audit_step["env"]["CLOUDFLARE_API_TOKEN"]
    assert "POSTGRES_PITR_REQUIRED" in audit_step["env"]
    assert audit_step["env"]["CHECK_PUBLIC_READY"] == "false"
    assert "scripts/ha/check_api_ha_readiness.sh" in audit_step["run"]
    assert "PRIMARY_SSH" in audit_step["run"]
    assert "STANDBY_SSH" in audit_step["run"]
    assert "api-ha-readiness.log" in audit_step["run"]
    assert "strict:" in summary_step["run"]
    assert artifact_step["if"] == "always()"
    assert artifact_step["with"]["path"] == "api-ha-readiness.log"


def test_ha_invariant_workflow_skips_public_cloudflare_challenge_from_runner():
    workflow = _workflow(".github/workflows/check-api-ha-invariants.yml")
    check_step = next(step for step in workflow["jobs"]["check"]["steps"] if step.get("name") == "Run active-passive invariant check")

    assert check_step["env"]["CHECK_PUBLIC_READY"] == "false"
    assert "scripts/ha/check_active_passive.sh" in check_step["run"]
