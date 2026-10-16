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


@pytest.fixture
def controller_main(monkeypatch, tmp_path):
    identity = tmp_path / "identity"
    identity.write_text("test-only-identity")
    identity.chmod(0o600)
    destination = tmp_path / "result.json"
    node = SimpleNamespace(alias="primary")
    runtime = SimpleNamespace(image="reviewed-image")
    monkeypatch.setattr(workflow.sys, "argv", ["controller", "plan", "--identity-file", str(identity),
                                             "--result-file", str(destination)])
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setattr(workflow.gates, "PATRONI_NODES", [node])
    monkeypatch.setattr(workflow.gates, "create_context", lambda *a: None)
    monkeypatch.setattr(workflow.gates, "validate_effective_config", lambda *a: None)
    monkeypatch.setattr(workflow.gates, "discover_cluster_topology", lambda **kw: SimpleNamespace(primary=node))
    monkeypatch.setattr(workflow.gates, "_reviewed_backend_image_for_sha", lambda sha: runtime.image)
    monkeypatch.setattr(workflow.gates, "_runtime_target_command", lambda *a, **kw: "probe")
    monkeypatch.setattr(workflow.gates, "_parse_runtime_target", lambda raw: runtime)
    monkeypatch.setattr(workflow, "command", lambda *a: "plan")
    monkeypatch.setattr(workflow.gates, "_run_remote", lambda *a, **kw: workflow.gates.RemoteOutput(0, json.dumps(result())))
    monkeypatch.setattr(workflow, "prove", lambda *a, **kw: {})
    return destination


@pytest.mark.parametrize("gate,expected", [
    ("create_context", "ssh_context"),
    ("validate_effective_config", "ssh_config"),
    ("discover_cluster_topology", "topology"),
    ("_reviewed_backend_image_for_sha", "reviewed_image"),
    ("_run_remote", "primary_runtime"),
    ("_parse_runtime_target", "primary_runtime"),
])
def test_early_failure_records_only_static_phase(monkeypatch, controller_main, capsys, gate, expected):
    sentinel = "SECRET_SENTINEL password_hash runtime_binding plan_token challenge"
    def fail(*args, **kwargs):
        raise RuntimeError(sentinel)
    monkeypatch.setattr(workflow.gates, gate, fail)
    with pytest.raises(SystemExit) as caught:
        workflow.main()
    assert caught.value.code == 2
    captured = capsys.readouterr()
    saved = controller_main.read_text()
    assert json.loads(saved) == {
        "operation": "plan", "outcome": "blocked", "failure_phase": expected,
        "reviewed_main_sha": "a" * 40,
    }
    assert captured.err == f"owner_profile_workflow status=blocked phase={expected}\n"
    assert not captured.out
    assert sentinel not in saved + captured.err


@pytest.mark.parametrize("transport_failure", [False, True])
def test_plan_transport_and_result_failures_are_distinct_and_private(
    monkeypatch, controller_main, capsys, transport_failure,
):
    sentinel = "PRIVATE_REMOTE_RESPONSE plan_token runtime_binding password_hash"
    def remote(node, context, command, **kwargs):
        if command == "probe":
            return workflow.gates.RemoteOutput(0, "runtime")
        if transport_failure:
            raise RuntimeError(sentinel)
        return workflow.gates.RemoteOutput(2, sentinel)
    monkeypatch.setattr(workflow.gates, "_run_remote", remote)
    with pytest.raises(SystemExit):
        workflow.main()
    expected = "primary_plan_transport" if transport_failure else "primary_plan_result"
    saved = controller_main.read_text()
    captured = capsys.readouterr()
    assert json.loads(saved)["failure_phase"] == expected
    assert f"phase={expected}" in captured.err
    assert sentinel not in saved + captured.err + captured.out


def test_successful_plan_still_writes_sanitized_report(controller_main, capsys):
    workflow.main()
    saved = controller_main.read_text()
    assert json.loads(saved)["result"]["ready"] is True
    assert json.loads(saved)["outcome"] == "completed"
    assert "private-plan-token" not in saved
    assert capsys.readouterr().err == ""


def test_unknown_failure_and_artifact_error_do_not_print_exception(monkeypatch, controller_main, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError("UNKNOWN_SECRET_SENTINEL")
    monkeypatch.setattr(workflow, "execute", fail)
    monkeypatch.setattr(workflow.gates, "_write_result", fail)
    with pytest.raises(SystemExit):
        workflow.main()
    captured = capsys.readouterr()
    assert captured.err == ("owner_profile_workflow artifact=unavailable\n"
                            "owner_profile_workflow status=blocked phase=unclassified\n")
    assert not captured.out


def test_failure_preserves_existing_recovery_report(monkeypatch, controller_main, capsys):
    report = {"operation": "execute", "outcome": "legacy_restored", "proof": {}}
    controller_main.write_text(json.dumps(report))
    def fail(args):
        raise workflow.PhaseError("PRIVATE_UNREVIEWED_PHASE")
    monkeypatch.setattr(workflow, "execute", fail)
    with pytest.raises(SystemExit):
        workflow.main()
    assert json.loads(controller_main.read_text()) == report
    assert capsys.readouterr().err == "owner_profile_workflow status=blocked phase=unclassified\n"


@pytest.mark.parametrize("code,status", [
    ("local_helper_unreviewed", None), ("remote_lock_busy", 1),
    ("remote_ssh_failed", 255), ("runtime_response_invalid", None),
])
def test_phase_preserves_safe_diagnostics_in_artifact_and_log(monkeypatch, controller_main, capsys, code, status):
    def fail(*args, **kwargs):
        error = workflow.gates.WorkflowDiagnosticError(code, remote_status=status)
        error.args = ("SECRET_SENTINEL exception contents",)
        raise error
    monkeypatch.setattr(workflow.gates, "_run_remote", fail)
    with pytest.raises(SystemExit):
        workflow.main()
    saved = controller_main.read_text()
    report = json.loads(saved)
    captured = capsys.readouterr()
    assert report["failure_phase"] == "primary_runtime"
    assert report["diagnostic_code"] == code
    if status is not None:
        assert report["remote_status"] == status
        assert f"remote_status={status}" in captured.err
    else:
        assert "remote_status" not in report
    assert f"diagnostic_code={code}" in captured.err
    assert "SECRET_SENTINEL" not in saved + captured.err + captured.out


def test_proof_failure_keeps_safe_remote_diagnostic(monkeypatch, controller_main, capsys):
    def fail(*args, **kwargs):
        raise workflow.gates.WorkflowDiagnosticError("remote_lock_busy", remote_status=1)
    monkeypatch.setattr(workflow, "prove", fail)
    with pytest.raises(SystemExit):
        workflow.main()
    report = json.loads(controller_main.read_text())
    assert report["failure_phase"] == "preflight_proof"
    assert report["diagnostic_code"] == "remote_lock_busy"
    assert report["remote_status"] == 1
    assert report["result"]["ready"] is False
    assert "private-plan-token" not in controller_main.read_text()
