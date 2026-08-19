from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/provision-tenant-manager.yml"


def _workflow() -> dict:
    return yaml.load(WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(workflow: dict, name: str) -> dict:
    return next(
        step for step in workflow["jobs"]["provision"]["steps"] if step.get("name") == name
    )


def test_workflow_is_manual_reviewed_main_only_and_serialized():
    config = _workflow()
    assert set(config["on"]) == {"workflow_dispatch"}
    assert config["concurrency"] == {
        "group": "production-release",
        "cancel-in-progress": "false",
    }
    job = config["jobs"]["provision"]
    assert job["environment"] == "production-api"
    assert job["permissions"] == {"contents": "read"}

    guard = _step(config, "Require Reviewed Main SHA And Explicit Operation")
    assert "refs/heads/main" in guard["run"]
    assert "CONFIRM_SHA" in guard["run"]
    assert "GITHUB_SHA" in guard["run"]
    assert "plan:false" in guard["run"]
    assert "execute:true" in guard["run"]


def test_workflow_has_validated_operation_and_apply_inputs():
    inputs = _workflow()["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {
        "confirm_sha",
        "operation",
        "apply",
        "tenant_slug",
        "storefront_slug",
        "display_name",
        "username",
        "phone",
        "reviewed_plan_digest",
    }
    assert inputs["operation"]["type"] == "choice"
    assert inputs["operation"]["options"] == ["plan", "execute"]
    assert inputs["apply"]["type"] == "boolean"
    assert inputs["apply"]["default"] == "false"
    for name in (
        "tenant_slug",
        "storefront_slug",
        "display_name",
        "username",
        "phone",
    ):
        assert inputs[name]["required"] == "true"


def test_workflow_uses_pinned_controller_and_static_one_time_secret():
    config = _workflow()
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    checkout = _step(config, "Checkout Exact Reviewed Main SHA")
    plan = _step(config, "Create Read-Only Provisioning Plan")
    execute = _step(config, "Execute Reviewed Provisioning Plan")

    assert checkout["uses"] == (
        "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10"
    )
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["persist-credentials"] == "false"
    assert "TENANT_MANAGER_ONE_TIME_PASSWORD" not in plan.get("env", {})
    assert execute["env"]["TENANT_MANAGER_ONE_TIME_PASSWORD"] == (
        "${{ secrets.TENANT_MANAGER_ONE_TIME_PASSWORD }}"
    )
    assert "printf '%s' \"${TENANT_MANAGER_ONE_TIME_PASSWORD}\" |" in execute["run"]
    assert "::add-mask::%s" in execute["run"]
    assert "%0A" in execute["run"]
    assert "--password-env" not in source
    assert "--plan-token" not in source
    assert "ssh-keyscan" not in source
    assert "secrets[" not in source


def test_uploaded_artifact_is_short_lived_sanitized_result_only():
    config = _workflow()
    upload = _step(config, "Upload Sanitized Operation Result")
    assert upload["uses"] == (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    )
    assert upload["with"]["path"] == "tenant-manager-operation-result.json"
    assert upload["with"]["retention-days"] == "3"
