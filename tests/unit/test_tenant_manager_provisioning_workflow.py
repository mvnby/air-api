from __future__ import annotations

import argparse
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha.pitr_pinned_ssh import PATRONI_NODES
from scripts.ha.pitr_cluster_topology import ClusterTopology
from scripts.ops import tenant_manager_provisioning_workflow as workflow


def _arguments(tmp_path: Path, *, operation: str = "plan") -> argparse.Namespace:
    identity = tmp_path / "identity"
    identity.write_text("private-key", encoding="utf-8")
    identity.chmod(0o600)
    return argparse.Namespace(
        operation=operation,
        tenant_slug="polotsk",
        storefront_slug="main",
        display_name="Андрей",
        username="andrey.polotsk",
        phone="+375297146293",
        reviewed_plan_digest=("a" * 64 if operation == "execute" else None),
        identity_file=identity,
        result_file=tmp_path / "result.json",
    )


def _plan_payload(
    *,
    ready: bool = True,
    digest: str = "a" * 64,
    changes: list[str] | None = None,
) -> str:
    effective_changes = (
        changes
        if changes is not None
        else (
            ["create_staff_user", "create_active_manager_membership"]
            if ready
            else []
        )
    )
    return json.dumps(
        {
            "mode": "plan",
            "ready": ready,
            "target": {
                "tenant_slug": "polotsk",
                "storefront_slug": "main",
                "display_name": "Андрей",
                "username": "andrey.polotsk",
                "phone": "+375297146293",
            },
            "current": {
                "tenant": {"id": 2, "status": "active", "is_system": False},
                "storefront": {
                    "id": 3,
                    "tenant_id": 2,
                    "status": "active",
                    "is_default": True,
                },
                "staff_users": [],
                "memberships": [],
            },
            "blockers": [] if ready else ["review required"],
            "changes": effective_changes,
            "plan_digest": digest,
            "plan_token": "fresh-plan-token",
            "plan_token_max_age_seconds": 900,
            "reviewed_execute_command": (
                "must never reach artifact" if ready else None
            ),
        }
    )


def _runtime_identity() -> str:
    return (
        "app-blue|"
        + "c" * 64
        + "|ghcr.io/mvnby/air-api/backend@sha256:"
        + "d" * 64
    )


def _topology(*, timeline: int = 20) -> ClusterTopology:
    return ClusterTopology(
        primary=PATRONI_NODES[0],
        standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789",
        timeline=timeline,
    )


def test_workflow_inputs_are_exact_and_execute_requires_reviewed_digest(tmp_path: Path):
    workflow.validate_arguments(_arguments(tmp_path))
    workflow.validate_arguments(_arguments(tmp_path, operation="execute"))

    invalid = _arguments(tmp_path, operation="execute")
    invalid.reviewed_plan_digest = "short"
    with pytest.raises(workflow.WorkflowError, match="reviewed plan digest"):
        workflow.validate_arguments(invalid)

    invalid = _arguments(tmp_path)
    invalid.username = "andrey; echo unsafe"
    with pytest.raises(workflow.WorkflowError, match="username"):
        workflow.validate_arguments(invalid)


def test_remote_command_is_fixed_to_active_immutable_app_and_reviewed_cli():
    node = PATRONI_NODES[0]
    runtime = workflow.RuntimeTarget(
        service="app-blue",
        container_id="c" * 64,
        image="ghcr.io/mvnby/air-api/backend@sha256:" + "d" * 64,
    )
    command = workflow._provisioning_command(
        node,
        runtime=runtime,
        operation="execute",
        tenant_slug="polotsk",
        storefront_slug="main",
        display_name="Андрей",
        username="andrey.polotsk",
        phone="+375297146293",
    )

    assert "http://127.0.0.1:8008/leader" in command
    assert ".active-api-slot" in command
    assert 'active_service="app-${active_slot}"' in command
    assert "scripts/provision_tenant_manager.py execute" in command
    assert "--execution-json-stdin" in command
    assert "--plan-token" not in command
    assert "--password-env" not in command
    assert "/bin/bash -c" not in command

    assert "docker exec -i " + "c" * 64 in command
    assert 'test "${container_id}" = ' + "c" * 64 in command
    assert runtime.image in command

    image_command = workflow._runtime_target_command(node)
    assert "provision_tenant_manager.py" not in image_command
    assert "{{.Config.Image}}" in image_command
    capability_command = workflow._runtime_capability_command(node, runtime=runtime)
    assert "--execution-json-stdin" in capability_command
    assert "docker exec -i " + "c" * 64 in capability_command


def test_runtime_target_requires_exact_container_and_immutable_image():
    runtime = workflow._parse_runtime_target(
        "app-green|" + "a" * 64 + "|ghcr.io/mvnby/air-api/backend@sha256:" + "b" * 64
    )
    assert runtime.service == "app-green"
    assert runtime.container_id == "a" * 64

    with pytest.raises(workflow.WorkflowError, match="container identity"):
        workflow._parse_runtime_target(
            "app-green|short|ghcr.io/mvnby/air-api/backend@sha256:" + "b" * 64
        )


def test_plan_sanitizer_removes_all_replay_material():
    sanitized, token = workflow.sanitize_plan(
        {
            "mode": "plan",
            "ready": True,
            "target": {},
            "current": {},
            "blockers": [],
            "plan_digest": "b" * 64,
            "plan_token": "sensitive-token",
            "plan_token_max_age_seconds": 900,
            "reviewed_execute_command": "execute --plan-token sensitive-token",
            "changes": [
                "create_staff_user",
                "create_active_manager_membership",
            ],
        }
    )

    assert token == "sensitive-token"
    assert "plan_token" not in sanitized
    assert "reviewed_execute_command" not in sanitized
    assert "sensitive-token" not in str(sanitized)


def test_blocked_plan_status_is_accepted_only_for_parseable_plan(monkeypatch):
    node = PATRONI_NODES[0]
    context = SimpleNamespace(config_file=Path("/tmp/reviewed-ssh-config"))
    captured_command: list[str] = []

    def runner(command, stdin):
        captured_command.extend(command)
        return subprocess.CompletedProcess(command, 2, _plan_payload(ready=False), "")

    monkeypatch.setattr(
        workflow,
        "_subprocess_runner",
        runner,
    )
    output = workflow._run_remote(
        node,
        context,
        "fixed command",
        accepted_statuses=frozenset({0, 2}),
    )
    result = workflow._load_result(output.stdout, expected_mode="plan")
    workflow._validate_result_semantics(
        result,
        expected_mode="plan",
        remote_status=output.status,
    )
    assert result["ready"] is False
    assert str(workflow.REMOTE_DEPLOY_LOCK_HELPER) in captured_command[-1]


def test_result_schema_drift_and_nested_secret_material_fail_closed():
    with pytest.raises(workflow.WorkflowError, match="schema is not reviewed"):
        workflow._load_result(
            '{"mode":"execute","ready":true,"changed":true,"target":{},'
            '"staff_user_id":1,"membership_id":2,"debug":"unsafe"}',
            expected_mode="execute",
        )
    with pytest.raises(workflow.WorkflowError, match="forbidden secret"):
        workflow._assert_no_forbidden_artifact_keys(
            {"safe": {"password": "must-not-upload"}}
        )

    valid_plan = json.loads(_plan_payload())
    valid_plan["ready"] = "true"
    with pytest.raises(workflow.WorkflowError, match="ready state"):
        workflow._validate_result_semantics(
            valid_plan,
            expected_mode="plan",
            remote_status=0,
        )

    valid_plan = json.loads(_plan_payload())
    with pytest.raises(workflow.WorkflowError, match="exit status"):
        workflow._validate_result_semantics(
            valid_plan,
            expected_mode="plan",
            remote_status=2,
        )

    partial_plan = json.loads(_plan_payload())
    partial_plan["changes"] = ["create_staff_user"]
    with pytest.raises(workflow.WorkflowError, match="change list"):
        workflow._validate_result_semantics(
            partial_plan,
            expected_mode="plan",
            remote_status=0,
        )


def test_password_is_read_only_from_bounded_stdin():
    assert workflow._read_password(io.BytesIO(b"generated-password-2026\n")) == (
        "generated-password-2026"
    )
    with pytest.raises(workflow.WorkflowError, match="password_too_long"):
        workflow._read_password(io.BytesIO(b"x" * 73))


def test_digest_mismatch_never_reaches_remote_execute(tmp_path: Path, monkeypatch):
    args = _arguments(tmp_path, operation="execute")
    args.reviewed_plan_digest = "f" * 64
    remote_commands: list[str] = []
    responses = iter(
        [
            workflow.RemoteOutput(0, _runtime_identity()),
            workflow.RemoteOutput(0, ""),
            workflow.RemoteOutput(0, _plan_payload()),
        ]
    )

    monkeypatch.setattr(workflow, "create_context", lambda *args: object())
    monkeypatch.setattr(workflow, "validate_effective_config", lambda *args: None)
    monkeypatch.setattr(workflow, "discover_cluster_topology", lambda **kwargs: _topology())
    monkeypatch.setattr(workflow, "_read_password", lambda: "generated-password-2026")

    def remote(node, context, command, **kwargs):
        remote_commands.append(command)
        return next(responses)

    monkeypatch.setattr(workflow, "_run_remote", remote)
    with pytest.raises(workflow.WorkflowError, match="differs from the reviewed"):
        workflow.execute(args)
    assert not any("provision_tenant_manager.py execute" in item for item in remote_commands)


def test_topology_drift_never_reaches_remote_execute(tmp_path: Path, monkeypatch):
    args = _arguments(tmp_path, operation="execute")
    topologies = iter([_topology(), _topology(timeline=21)])
    remote_commands: list[str] = []
    responses = iter(
        [
            workflow.RemoteOutput(0, _runtime_identity()),
            workflow.RemoteOutput(0, ""),
            workflow.RemoteOutput(0, _plan_payload()),
        ]
    )

    monkeypatch.setattr(workflow, "create_context", lambda *args: object())
    monkeypatch.setattr(workflow, "validate_effective_config", lambda *args: None)
    monkeypatch.setattr(
        workflow,
        "discover_cluster_topology",
        lambda **kwargs: next(topologies),
    )
    monkeypatch.setattr(workflow, "_read_password", lambda: "generated-password-2026")

    def remote(node, context, command, **kwargs):
        remote_commands.append(command)
        return next(responses)

    monkeypatch.setattr(workflow, "_run_remote", remote)
    with pytest.raises(workflow.WorkflowError, match="topology changed"):
        workflow.execute(args)
    assert not any("provision_tenant_manager.py execute" in item for item in remote_commands)


def test_blocked_plan_writes_sanitized_review_artifact(tmp_path: Path, monkeypatch):
    args = _arguments(tmp_path)
    responses = iter(
        [
            workflow.RemoteOutput(0, _runtime_identity()),
            workflow.RemoteOutput(0, ""),
            workflow.RemoteOutput(2, _plan_payload(ready=False)),
        ]
    )

    monkeypatch.setattr(workflow, "create_context", lambda *args: object())
    monkeypatch.setattr(workflow, "validate_effective_config", lambda *args: None)
    monkeypatch.setattr(workflow, "discover_cluster_topology", lambda **kwargs: _topology())
    monkeypatch.setattr(
        workflow,
        "_run_remote",
        lambda node, context, command, **kwargs: next(responses),
    )

    artifact = workflow.execute(args)
    written = json.loads(args.result_file.read_text(encoding="utf-8"))
    assert artifact["result"]["ready"] is False
    assert written["result"]["blockers"] == ["review required"]
    assert "fresh-plan-token" not in str(written)
    assert "reviewed_execute_command" not in str(written)


def test_existing_compliant_manager_plan_is_noop_and_never_executes(
    tmp_path: Path, monkeypatch
):
    args = _arguments(tmp_path)
    no_op_plan = json.loads(_plan_payload(changes=[]))
    no_op_plan["current"] = {
        "tenant": {"id": 34, "status": "active", "is_system": False},
        "storefront": {
            "id": 35,
            "tenant_id": 34,
            "status": "active",
            "is_default": True,
        },
        "staff_users": [
            {
                "id": 36,
                "username": "andrey.polotsk",
                "display_name": "Андрей",
                "phone": "+375297146293",
                "status": "active",
                "primary_role": "manager",
                "roles": ["manager"],
                "legacy_installer_id": None,
                "telegram_id": None,
                "telegram_username": None,
            }
        ],
        "memberships": [
            {"id": 37, "tenant_id": 34, "role": "manager", "status": "active"}
        ],
    }
    remote_commands: list[str] = []
    responses = iter(
        [
            workflow.RemoteOutput(0, _runtime_identity()),
            workflow.RemoteOutput(0, ""),
            workflow.RemoteOutput(0, json.dumps(no_op_plan)),
        ]
    )

    monkeypatch.setattr(workflow, "create_context", lambda *args: object())
    monkeypatch.setattr(workflow, "validate_effective_config", lambda *args: None)
    monkeypatch.setattr(workflow, "discover_cluster_topology", lambda **kwargs: _topology())

    def remote(node, context, command, **kwargs):
        remote_commands.append(command)
        return next(responses)

    monkeypatch.setattr(workflow, "_run_remote", remote)

    artifact = workflow.execute(args)

    assert artifact["result"]["ready"] is True
    assert artifact["result"]["changes"] == []
    assert artifact["result"]["current"]["tenant"]["id"] == 34
    assert artifact["result"]["current"]["storefront"]["id"] == 35
    assert artifact["result"]["target"]["username"] == "andrey.polotsk"
    assert not any("provision_tenant_manager.py execute" in item for item in remote_commands)
    assert "fresh-plan-token" not in args.result_file.read_text(encoding="utf-8")


def test_secret_is_not_copied_into_subprocess_environment(monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.setenv("TENANT_MANAGER_ONE_TIME_PASSWORD", "never-in-child-env")

    def run(command, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(workflow.subprocess, "run", run)
    workflow._subprocess_runner(["ssh", "reviewed"], "secret-over-stdin")
    assert captured["input"] == "secret-over-stdin"
    assert "TENANT_MANAGER_ONE_TIME_PASSWORD" not in captured["env"]


def test_main_marks_blocked_plan_failed_after_artifact_is_written(monkeypatch):
    class Parser:
        @staticmethod
        def parse_args():
            return object()

    monkeypatch.setattr(workflow, "build_parser", lambda: Parser())
    monkeypatch.setattr(
        workflow,
        "execute",
        lambda args: {
            "operation": "plan",
            "primary_node": "mvn-api",
            "result": {"ready": False},
        },
    )
    with pytest.raises(SystemExit) as exc:
        workflow.main()
    assert exc.value.code == 2
