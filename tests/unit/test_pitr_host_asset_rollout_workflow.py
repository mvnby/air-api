from pathlib import Path
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _workflow() -> dict:
    return yaml.load(
        (
            REPO_ROOT
            / ".github/workflows/rollout-postgres-pitr-host-assets.yml"
        ).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def _step(workflow: dict, name: str) -> dict:
    return next(
        step
        for step in workflow["jobs"]["rollout"]["steps"]
        if step.get("name") == name
    )


def test_pitr_host_asset_rollout_is_manual_main_only_and_exact_sha_gated():
    workflow = _workflow()
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    assert workflow["concurrency"]["queue"] == "max"
    assert workflow["concurrency"]["group"] == "postgres-pitr-host-operations"

    guard = _step(workflow, "Require Reviewed Main SHA")
    assert "refs/heads/main" in guard["run"]
    assert "CONFIRM_SHA" in guard["run"]
    assert "GITHUB_SHA" in guard["run"]
    assert guard["env"]["CONFIRM_SHA"] == "${{ inputs.confirm_sha }}"


def test_pitr_host_asset_rollout_uses_pinned_checkout_and_stable_transaction():
    workflow = _workflow()
    checkout = _step(workflow, "Checkout")
    transaction = _step(workflow, "Derive Stable Transaction ID")

    assert checkout["uses"] == (
        "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10"
    )
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["persist-credentials"] == "false"
    assert "GITHUB_RUN_ID" in transaction["run"]
    assert "GITHUB_SHA" in transaction["run"]
    assert "GITHUB_RUN_ATTEMPT" not in transaction["run"]


def test_pitr_host_asset_rollout_uses_pinned_ssh_controller_and_retains_log():
    workflow = _workflow()
    rollout = _step(workflow, "Roll Out And Attest PITR Host Assets")
    artifact = _step(workflow, "Upload PITR Host-Asset Rollout Log")
    notify = _step(workflow, "Notify HA failure")

    assert rollout["env"]["SSH_KEY"] == "${{ secrets.SSH_KEY }}"
    assert "ssh-keyscan" not in rollout["run"]
    assert "rollout_postgres_pitr_host_assets.py" in rollout["run"]
    assert "--transaction-id" in rollout["run"]
    assert artifact["if"] == "always()"
    assert artifact["uses"] == (
        "actions/upload-artifact@"
        "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    )
    assert notify["if"] == "failure() && github.ref == 'refs/heads/main'"


def test_pitr_host_asset_controller_starts_under_isolated_python():
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(
                REPO_ROOT
                / "scripts/ha/rollout_postgres_pitr_host_assets.py"
            ),
            "--help",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--transaction-id" in result.stdout
