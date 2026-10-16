import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts.ops import owner_profile_consolidation_workflow as workflow


def result(action="plan"):
    data = {
        "mode": action, "ready": True, "complete": False,
        "source_staff_user_id": 1, "target_staff_user_id": 4,
        "blockers": [], "source_references": {"tenant_membership.staff_user_id": 1},
        "changes": ["transfer_personal_profile"], "preserve_target_auth_version": True,
        "plan_digest": "d" * 64,
    }
    data.update({"plan_token": "private-plan-token"} if action == "plan" else {"runtime_binding": "b" * 64})
    return data


@pytest.mark.parametrize("action", ["plan", "verify"])
def test_sensitive_proof_values_never_reach_artifact(action):
    data = result(action)
    parsed = workflow.parse_result(workflow.gates.RemoteOutput(0, json.dumps(data)), action=action)
    sanitized = workflow.sanitize(parsed)
    assert set(sanitized) == workflow.PUBLIC_KEYS
    assert "private-plan-token" not in json.dumps(sanitized)
    assert "b" * 64 not in json.dumps(sanitized)
    for key in ("password_hash", "binding_challenge", "recovery_binding"):
        bad = {**data, key: "sensitive"}
        with pytest.raises(workflow.gates.WorkflowError):
            workflow.parse_result(workflow.gates.RemoteOutput(0, json.dumps(bad)), action=action)


def test_result_rejects_wrong_identity_and_exit_status():
    data = result()
    data["target_staff_user_id"] = 5
    with pytest.raises(workflow.gates.WorkflowError):
        workflow.parse_result(workflow.gates.RemoteOutput(0, json.dumps(data)), action="plan")
    with pytest.raises(workflow.gates.WorkflowError):
        workflow.parse_result(workflow.gates.RemoteOutput(2, json.dumps(result())), action="plan")


def test_workflow_requires_reviewed_main_and_no_credential_input():
    path = Path(__file__).resolve().parents[2] / ".github/workflows/consolidate-owner-profile.yml"
    content = path.read_text()
    config = yaml.load(content, Loader=yaml.BaseLoader)
    assert set(config["on"]) == {"workflow_dispatch"}
    assert set(config["on"]["workflow_dispatch"]["inputs"]) == {"confirm_sha", "operation", "apply", "reviewed_plan_digest"}
    assert config["concurrency"]["group"] == "production-release"
    assert config["jobs"]["consolidate"]["environment"] == "production-api"
    assert "refs/heads/main" in content and '"${CONFIRM_SHA}" != "${GITHUB_SHA}"' in content
    assert "plan:false" in content and "execute:true" in content
    assert "--workflow ci.yml" in content and '--commit "${GITHUB_SHA}"' in content
    assert "ONE_TIME_PASSWORD" not in content and "credential-stdin" not in content
    assert "--reviewed-plan-digest" in content and "ssh-keyscan" not in content


def test_dual_node_proof_rejects_different_recovery_credentials(monkeypatch):
    primary, standby = SimpleNamespace(alias="primary"), SimpleNamespace(alias="standby")
    runtime = SimpleNamespace(image="reviewed-image")
    monkeypatch.setattr(workflow.gates, "_runtime_target_command", lambda *a, **kw: "probe")
    monkeypatch.setattr(workflow.gates, "_run_remote", lambda *a, **kw: SimpleNamespace(stdout="runtime"))
    monkeypatch.setattr(workflow.gates, "_parse_runtime_target", lambda raw: runtime)
    def proof(node, *args):
        return {**result("verify"), "runtime_binding": ("a" if node is primary else "b") * 64}
    monkeypatch.setattr(workflow, "request", proof)
    with pytest.raises(workflow.gates.WorkflowError, match="credentials disagree"):
        workflow.prove(None, SimpleNamespace(primary=primary, standby=standby), "reviewed-image", "c" * 64)


def test_execute_stale_review_never_dispatches_mutation(monkeypatch, tmp_path):
    identity = tmp_path / "identity"
    identity.write_text("test-only-identity")
    identity.chmod(0o600)
    args = SimpleNamespace(operation="execute", identity_file=identity, result_file=tmp_path / "result.json", reviewed_plan_digest="e" * 64)
    topology = SimpleNamespace(primary=SimpleNamespace(alias="primary"))
    monkeypatch.setattr(workflow.gates, "PATRONI_NODES", [])
    monkeypatch.setattr(workflow.gates, "create_context", lambda *a: None)
    monkeypatch.setattr(workflow.gates, "discover_cluster_topology", lambda **kw: topology)
    monkeypatch.setattr(workflow.gates, "_reviewed_backend_image_for_sha", lambda sha: "reviewed-image")
    monkeypatch.setattr(workflow.gates, "_runtime_target_command", lambda *a, **kw: "probe")
    monkeypatch.setattr(workflow.gates, "_run_remote", lambda *a, **kw: SimpleNamespace(stdout="runtime"))
    monkeypatch.setattr(workflow.gates, "_parse_runtime_target", lambda raw: SimpleNamespace(image="reviewed-image"))
    monkeypatch.setattr(workflow, "prove", lambda *a, **kw: {})
    actions = []
    def request(*args):
        actions.append(args[4])
        return result()
    monkeypatch.setattr(workflow, "request", request)
    with pytest.raises(workflow.gates.WorkflowError, match="differs"):
        workflow.execute(args)
    assert actions == ["plan"]
