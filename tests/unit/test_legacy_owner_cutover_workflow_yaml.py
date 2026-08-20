from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/cutover-legacy-owner.yml"


def _workflow() -> dict:
    return yaml.load(WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(config: dict, name: str) -> dict:
    return next(step for step in config["jobs"]["cutover"]["steps"] if step.get("name") == name)


def test_workflow_is_manual_reviewed_main_only_and_serialized():
    config = _workflow()
    assert set(config["on"]) == {"workflow_dispatch"}
    assert config["concurrency"] == {"group": "production-release", "cancel-in-progress": "false"}
    job = config["jobs"]["cutover"]
    assert job["environment"] == "production-api"
    assert job["permissions"] == {
        "actions": "read", "contents": "read", "packages": "read"
    }
    guard = _step(config, "Require Reviewed Main SHA And Explicit Operation")["run"]
    assert "refs/heads/main" in guard
    assert "GITHUB_SHA" in guard
    assert "plan:false" in guard
    assert "execute:true|rollback:true" in guard


def test_workflow_requires_exactly_one_successful_ci_run_for_reviewed_sha():
    config = _workflow()
    gate = _step(config, "Require Exact Successful Main CI")
    assert gate["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "--workflow ci.yml" in gate["run"]
    assert "--branch main" in gate["run"]
    assert "--commit \"${GITHUB_SHA}\"" in gate["run"]
    assert "--status success" in gate["run"]
    assert "--limit 100" in gate["run"]
    assert '"${successful_run_count}" != "1"' in gate["run"]


def test_workflow_has_no_target_or_secret_credential_inputs():
    inputs = _workflow()["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"confirm_sha", "operation", "plan_for", "apply", "reviewed_plan_digest"}
    assert inputs["operation"]["options"] == ["plan", "execute", "rollback"]
    assert inputs["plan_for"]["options"] == ["cutover", "rollback"]
    assert inputs["apply"]["default"] == "false"
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "ADMIN_PASSWORD" not in source
    assert "ADMIN_USERNAME" not in source
    assert "--password-env" not in source
    assert "ssh-keyscan" not in source
    assert "secrets[" not in source


def test_workflow_uses_pinned_checkout_and_short_lived_sanitized_artifact():
    config = _workflow()
    checkout = _step(config, "Checkout Exact Reviewed Main SHA")
    assert checkout["uses"] == "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10"
    assert checkout["with"] == {"ref": "${{ github.sha }}", "persist-credentials": "false"}
    upload = _step(config, "Upload Sanitized Operation Result")
    assert upload["uses"] == "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    assert upload["with"]["path"] == "legacy-owner-cutover-result.json"
    assert upload["with"]["retention-days"] == "3"
    assert upload["with"]["if-no-files-found"] == "error"
    assert "ADMIN_* removal: not part" in _step(config, "Write Sanitized Summary")["run"]
    registry_login = _step(config, "Authenticate GHCR Metadata Reader")
    assert registry_login["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "docker login ghcr.io" in registry_login["run"]
    assert "--password-stdin" in registry_login["run"]
