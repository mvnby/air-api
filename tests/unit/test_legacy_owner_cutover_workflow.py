import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest

from scripts.ha.pitr_cluster_topology import ClusterTopology
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES
from scripts.ops import legacy_owner_cutover_workflow as workflow


def _arguments(tmp_path: Path, *, operation: str = "plan") -> argparse.Namespace:
    identity = tmp_path / "identity"
    identity.write_text("private-key", encoding="utf-8")
    identity.chmod(0o600)
    return argparse.Namespace(
        operation=operation,
        plan_for="cutover",
        reviewed_plan_digest=("a" * 64 if operation != "plan" else None),
        credential_stdin=operation == "execute",
        identity_file=identity,
        result_file=tmp_path / "result.json",
    )


def _runtime() -> workflow.RuntimeTarget:
    return workflow.RuntimeTarget(
        service="app-blue", container_id="a" * 64,
        image="ghcr.io/mvnby/air-api/backend@sha256:" + "b" * 64,
    )


def test_arguments_are_fixed_and_mutations_require_reviewed_digest(tmp_path: Path):
    workflow.validate_arguments(_arguments(tmp_path))
    workflow.validate_arguments(_arguments(tmp_path, operation="execute"))
    invalid = _arguments(tmp_path, operation="rollback")
    invalid.reviewed_plan_digest = "short"
    with pytest.raises(workflow.WorkflowError, match="reviewed plan digest"):
        workflow.validate_arguments(invalid)
    rollback_plan = _arguments(tmp_path)
    rollback_plan.plan_for = "rollback"
    workflow.validate_arguments(rollback_plan)
    invalid = _arguments(tmp_path, operation="execute")
    invalid.plan_for = "rollback"
    with pytest.raises(workflow.WorkflowError, match="plan-for override"):
        workflow.validate_arguments(invalid)


def test_remote_commands_are_fixed_to_active_immutable_container_and_cli():
    node = PATRONI_NODES[0]
    command = workflow._cutover_command(
        node, runtime=_runtime(), role="primary", action="execute"
    )
    assert "scripts/cutover_legacy_owner.py execute --execution-json-stdin" in command
    assert "--plan-token" not in command
    assert "ADMIN_PASSWORD" not in command
    assert "http://127.0.0.1:8008/leader" in command
    assert ".active-api-slot" in command
    assert "docker exec -i " + "a" * 64 in command
    assert _runtime().image in command
    assert "--for-action rollback" in workflow._cutover_command(
        node, runtime=_runtime(), role="primary", action="plan", token="rollback"
    )
    credential_proof = workflow._cutover_command(
        node,
        runtime=_runtime(),
        role="primary",
        action="verify",
        prove_credential=True,
    )
    assert "--credential-json-stdin" in credential_proof
    assert "new_password" not in credential_proof


def test_runtime_rejects_nonimmutable_or_malformed_container_identity():
    parsed = workflow._parse_runtime_target(
        "app-green|" + "c" * 64 + "|ghcr.io/mvnby/air-api/backend@sha256:" + "d" * 64
    )
    assert parsed.service == "app-green"
    with pytest.raises(workflow.WorkflowError, match="reviewed immutable"):
        workflow._parse_runtime_target("app-blue|" + "c" * 64 + "|backend:latest")


def test_one_time_credential_reader_is_bounded_and_does_not_normalize_bytes():
    assert workflow._read_one_time_credential(BytesIO("Пароль-2026".encode())) == (
        "Пароль-2026"
    )
    with pytest.raises(workflow.WorkflowError, match="too large"):
        workflow._read_one_time_credential(
            BytesIO(b"x" * (workflow.MAX_ONE_TIME_CREDENTIAL_BYTES + 1))
        )


def test_reviewed_sha_tag_is_resolved_to_exact_immutable_backend_digest(monkeypatch):
    raw = b'{"schemaVersion":2}'
    sha = "a" * 40
    provenance = json.dumps(
        {
            "SLSA": {
                "buildDefinition": {}, "runDetails": {},
                "vcs:source": "https://github.com/mvnby/air-api",
                "vcs:revision": sha,
            }
        }
    ).encode()

    class Completed:
        def __init__(self, stdout: bytes):
            self.stdout = stdout

    captured: list[list[str]] = []
    outputs = iter([raw, provenance])
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda command, **kwargs: captured.append(command) or Completed(next(outputs)),
    )
    assert workflow._reviewed_backend_image_for_sha(sha) == (
        "ghcr.io/mvnby/air-api/backend@sha256:" + hashlib.sha256(raw).hexdigest()
    )
    assert captured[0][4] == f"ghcr.io/mvnby/air-api/backend:{sha}"
    assert captured[1][4].endswith("@sha256:" + hashlib.sha256(raw).hexdigest())


def test_reviewed_sha_image_rejects_missing_or_wrong_build_provenance(monkeypatch):
    raw = b'{"schemaVersion":2}'

    class Completed:
        def __init__(self, stdout: bytes):
            self.stdout = stdout

    for provenance in (b"null", b"{}", json.dumps({"SLSA": {"buildDefinition": {}, "runDetails": {}, "vcs:source": "https://github.com/mvnby/air-api", "vcs:revision": "b" * 40}}).encode()):
        outputs = iter([raw, provenance])
        monkeypatch.setattr(
            workflow.subprocess,
            "run",
            lambda command, **kwargs: Completed(next(outputs)),
        )
        with pytest.raises(workflow.WorkflowError, match="provenance"):
            workflow._reviewed_backend_image_for_sha("a" * 40)


def test_standby_proof_uses_replica_endpoint_not_primary_leader_endpoint():
    command = workflow._runtime_target_command(PATRONI_NODES[1], role="standby")
    assert "/replica" in command
    assert "/leader" not in command


def test_automatic_rollback_refuses_to_mutate_after_patroni_failover(monkeypatch):
    reviewed = ClusterTopology(
        primary=PATRONI_NODES[0], standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789", timeline=1,
    )
    failover = ClusterTopology(
        primary=PATRONI_NODES[1], standby=PATRONI_NODES[0],
        system_identifier="1234567890123456789", timeline=2,
    )
    calls: list[object] = []
    monkeypatch.setattr(
        workflow, "discover_cluster_topology", lambda **kwargs: failover
    )
    monkeypatch.setattr(workflow, "_run_remote", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(workflow.WorkflowError, match="topology changed"):
        workflow._automatic_rollback(
            object(), reviewed, _runtime().image, binding_challenge="c" * 64
        )
    assert calls == []


def test_automatic_rollback_refuses_changed_runtime_image(monkeypatch):
    topology = ClusterTopology(
        primary=PATRONI_NODES[0], standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789", timeline=1,
    )
    monkeypatch.setattr(
        workflow, "discover_cluster_topology", lambda **kwargs: topology
    )
    monkeypatch.setattr(
        workflow, "_run_remote",
        lambda *args, **kwargs: workflow.RemoteOutput(
            0,
            "app-blue|" + "c" * 64
            + "|ghcr.io/mvnby/air-api/backend@sha256:" + "d" * 64,
        ),
    )
    with pytest.raises(workflow.WorkflowError, match="runtime image changed"):
        workflow._automatic_rollback(
            object(), topology, _runtime().image, binding_challenge="c" * 64
        )


def test_dual_node_proof_refuses_standby_image_different_from_reviewed_primary(monkeypatch):
    topology = ClusterTopology(
        primary=PATRONI_NODES[0], standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789", timeline=1,
    )
    verified = json.dumps(
        {
            "mode": "verify", "ready": True, "blockers": [], "staff_user_id": 1,
            "membership_id": 2, "system_tenant_id": 3, "system_storefront_id": 4,
            "auth_mode": "staff_shadow", "legacy_token_version": 2,
                "credential_matches": True, "can_change_password": True,
                "auth_source_staff_password": True, "legacy_jwt_rejected": True,
                "legacy_google_auth_rejected": True, "runtime_binding": "e" * 64,
        }
    )
    good = "app-blue|" + "a" * 64 + "|" + _runtime().image
    changed = "app-green|" + "b" * 64 + "|ghcr.io/mvnby/air-api/backend@sha256:" + "c" * 64
    outputs = iter([
        workflow.RemoteOutput(0, good), workflow.RemoteOutput(0, verified),
        workflow.RemoteOutput(0, changed),
    ])
    monkeypatch.setattr(workflow, "_run_remote", lambda *args, **kwargs: next(outputs))
    with pytest.raises(workflow.WorkflowError, match="image differs"):
        workflow._proof_all_nodes(
            object(),
            topology,
            expected_image=_runtime().image,
            staff_credential="one-time-owner-password-2026",
            binding_challenge="c" * 64,
        )


def test_dual_node_staff_proof_sends_credential_only_over_stdin_and_sanitizes_it(
    monkeypatch,
):
    topology = ClusterTopology(
        primary=PATRONI_NODES[0], standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789", timeline=1,
    )
    password = "one-time-owner-password-2026"
    runtime = "app-blue|" + "a" * 64 + "|" + _runtime().image
    verified = _verify_payload(mode="staff_shadow")
    outputs = iter([
        workflow.RemoteOutput(0, runtime), workflow.RemoteOutput(0, verified),
        workflow.RemoteOutput(0, runtime), workflow.RemoteOutput(0, verified),
    ])
    calls: list[dict] = []

    def run_remote(*args, **kwargs):
        calls.append(kwargs)
        return next(outputs)

    monkeypatch.setattr(workflow, "_run_remote", run_remote)
    proof = workflow._proof_all_nodes(
        object(),
        topology,
        expected_image=_runtime().image,
        staff_credential=password,
        binding_challenge="c" * 64,
    )
    credential_inputs = [call["stdin"] for call in calls if call.get("stdin")]
    assert len(credential_inputs) == 2
    assert all(
        json.loads(value)
        == {"binding_challenge": "c" * 64, "new_password": password}
        for value in credential_inputs
    )
    assert password not in json.dumps(proof)


def test_standby_verification_retries_until_replication_reaches_shadow(
    monkeypatch,
) -> None:
    outputs = iter([
        workflow.RemoteOutput(0, _verify_payload(mode="legacy")),
        workflow.RemoteOutput(0, _verify_payload(mode="staff_shadow")),
    ])
    calls: list[object] = []
    monkeypatch.setattr(
        workflow,
        "_run_remote",
        lambda *args, **kwargs: calls.append((args, kwargs)) or next(outputs),
    )
    monkeypatch.setattr(workflow.time, "sleep", lambda _seconds: None)

    result = workflow._verify_node(
        node=PATRONI_NODES[1],
        context=object(),
        runtime=_runtime(),
        role="standby",
        payload=json.dumps(
            {"binding_challenge": "c" * 64, "new_password": "long-password"}
        ),
        expected_modes=frozenset({"staff_shadow"}),
    )

    assert result["auth_mode"] == "staff_shadow"
    assert len(calls) == 2


def _plan_payload() -> dict:
    return {
        "mode": "plan", "ready": True,
        "target": {"system_tenant_slug": "mvn", "system_storefront_slug": "main"},
        "current": {"auth_mode": "legacy"}, "blockers": [],
        "changes": ["activate_staff_shadow"], "plan_digest": "a" * 64,
        "plan_token": "signed-token", "plan_token_max_age_seconds": 900,
    }


def _verify_payload(
    *,
    mode: str,
    binding: str = "e" * 64,
    has_bound_identity: bool = True,
    ready: bool = True,
    blockers: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "mode": "verify", "ready": ready,
            "blockers": blockers or [],
            "staff_user_id": 1 if has_bound_identity else None,
            "membership_id": 2 if has_bound_identity else None,
            "system_tenant_id": 3, "system_storefront_id": 4,
            "auth_mode": mode, "legacy_token_version": 2,
            "credential_matches": True, "can_change_password": mode != "legacy",
            "auth_source_staff_password": mode != "legacy",
            "legacy_jwt_rejected": mode != "legacy",
            "legacy_google_auth_rejected": mode != "legacy",
            "runtime_binding": binding,
        }
    )


def test_failed_node_verification_logs_only_safe_blocker_codes(
    monkeypatch, capsys,
) -> None:
    blocked = _verify_payload(
        mode="staff_shadow",
        ready=False,
        blockers=["staff_credential_unproved"],
    )
    monkeypatch.setattr(
        workflow,
        "_run_remote",
        lambda *args, **kwargs: workflow.RemoteOutput(2, blocked),
    )
    with pytest.raises(workflow.WorkflowError, match="did not reach"):
        workflow._verify_node(
            node=PATRONI_NODES[0], context=object(), runtime=_runtime(),
            role="primary", payload="{}",
            expected_modes=frozenset({"staff_shadow"}),
        )
    error = capsys.readouterr().err
    assert "blockers=staff_credential_unproved" in error
    assert "password" not in error


def _rollback_payload() -> str:
    return json.dumps(
        {
            "mode": "rollback", "ready": True, "changed": True,
            "staff_user_id": 1, "membership_id": 2, "system_tenant_id": 3,
            "system_storefront_id": 4, "auth_mode": "legacy",
            "legacy_token_version": 3, "plan_digest": "a" * 64,
        }
    )


def test_malformed_execute_result_runs_recovery_for_already_committed_shadow(monkeypatch, tmp_path: Path):
    args = _arguments(tmp_path, operation="execute")
    topology = ClusterTopology(
        primary=PATRONI_NODES[0], standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789", timeline=1,
    )
    good_runtime = "app-blue|" + "a" * 64 + "|" + _runtime().image
    outputs = iter([
        workflow.RemoteOutput(0, good_runtime),  # initial primary runtime
        workflow.RemoteOutput(0, good_runtime), workflow.RemoteOutput(0, ""),
        workflow.RemoteOutput(0, "app-green|" + "b" * 64 + "|" + _runtime().image), workflow.RemoteOutput(0, ""),
        workflow.RemoteOutput(0, good_runtime), workflow.RemoteOutput(0, _verify_payload(mode="legacy")),
        workflow.RemoteOutput(0, "app-green|" + "b" * 64 + "|" + _runtime().image), workflow.RemoteOutput(0, _verify_payload(mode="legacy")),
        workflow.RemoteOutput(0, "malformed-after-commit"),
        workflow.RemoteOutput(0, good_runtime), workflow.RemoteOutput(0, ""),
        workflow.RemoteOutput(0, _verify_payload(mode="staff_shadow")),
    ])
    recovered: list[object] = []
    monkeypatch.setattr(workflow, "create_context", lambda *args: object())
    monkeypatch.setattr(workflow, "validate_effective_config", lambda *args: None)
    monkeypatch.setattr(workflow, "discover_cluster_topology", lambda **kwargs: topology)
    monkeypatch.setattr(workflow, "_reviewed_backend_image_for_sha", lambda *args: _runtime().image)
    monkeypatch.setattr(
        workflow,
        "_fresh_plan",
        lambda *args, **kwargs: (_plan_payload(), "signed-token"),
    )
    monkeypatch.setattr(
        workflow,
        "_read_one_time_credential",
        lambda: "one-time-owner-password-2026",
    )
    monkeypatch.setattr(workflow, "_run_remote", lambda *args, **kwargs: next(outputs))
    monkeypatch.setattr(
        workflow,
        "_automatic_rollback",
        lambda *args, **kwargs: recovered.append((args, kwargs))
        or {"zakup": {"result": {}}, "mvn-api": {"result": {}}},
    )
    with pytest.raises(workflow.WorkflowError, match="automatic recovery completed"):
        workflow.execute(args)
    assert recovered and recovered[0][0][1] == topology
    failure_artifact = json.loads(args.result_file.read_text(encoding="utf-8"))
    assert failure_artifact["outcome"] == "recovered"
    assert failure_artifact["recovery"] == "legacy_restored"
    assert "runtime_binding" not in json.dumps(failure_artifact)


def test_rollback_proof_checks_legacy_mode_on_both_primary_and_standby(monkeypatch):
    topology = ClusterTopology(
        primary=PATRONI_NODES[0], standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789", timeline=1,
    )
    primary = "app-blue|" + "a" * 64 + "|" + _runtime().image
    standby = "app-green|" + "b" * 64 + "|" + _runtime().image
    outputs = iter([
        workflow.RemoteOutput(0, primary), workflow.RemoteOutput(0, _verify_payload(mode="legacy")),
        workflow.RemoteOutput(0, standby), workflow.RemoteOutput(0, _verify_payload(mode="legacy")),
    ])
    monkeypatch.setattr(workflow, "_run_remote", lambda *args, **kwargs: next(outputs))
    proof = workflow._verify_legacy_after_rollback(
        object(),
        topology,
        expected_image=_runtime().image,
        binding_challenge="c" * 64,
    )
    assert set(proof) == {node.alias for node in PATRONI_NODES}


def test_initial_legacy_recovery_proof_allows_no_bound_staff_identity(monkeypatch):
    topology = ClusterTopology(
        primary=PATRONI_NODES[0], standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789", timeline=1,
    )
    primary = "app-blue|" + "a" * 64 + "|" + _runtime().image
    standby = "app-green|" + "b" * 64 + "|" + _runtime().image
    outputs = iter([
        workflow.RemoteOutput(0, primary),
        workflow.RemoteOutput(
            0,
            _verify_payload(mode="legacy", has_bound_identity=False),
        ),
        workflow.RemoteOutput(0, standby),
        workflow.RemoteOutput(
            0,
            _verify_payload(mode="legacy", has_bound_identity=False),
        ),
    ])
    monkeypatch.setattr(workflow, "_run_remote", lambda *args, **kwargs: next(outputs))
    proof = workflow._verify_legacy_after_rollback(
        object(),
        topology,
        expected_image=_runtime().image,
        binding_challenge="c" * 64,
    )
    assert all(
        item["result"]["staff_user_id"] is None
        and item["result"]["membership_id"] is None
        for item in proof.values()
    )


def test_rollback_proof_refuses_different_secret_safe_runtime_bindings(monkeypatch):
    topology = ClusterTopology(
        primary=PATRONI_NODES[0], standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789", timeline=1,
    )
    primary = "app-blue|" + "a" * 64 + "|" + _runtime().image
    standby = "app-green|" + "b" * 64 + "|" + _runtime().image
    outputs = iter([
        workflow.RemoteOutput(0, primary), workflow.RemoteOutput(0, _verify_payload(mode="legacy", binding="e" * 64)),
        workflow.RemoteOutput(0, standby), workflow.RemoteOutput(0, _verify_payload(mode="legacy", binding="f" * 64)),
    ])
    monkeypatch.setattr(workflow, "_run_remote", lambda *args, **kwargs: next(outputs))
    with pytest.raises(workflow.WorkflowError, match="different local credential bindings"):
        workflow._verify_legacy_after_rollback(
            object(),
            topology,
            expected_image=_runtime().image,
            binding_challenge="c" * 64,
        )


def test_manual_rollback_writes_dual_node_legacy_proof_to_artifact(monkeypatch, tmp_path: Path):
    args = _arguments(tmp_path, operation="rollback")
    topology = ClusterTopology(
        primary=PATRONI_NODES[0], standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789", timeline=1,
    )
    primary = "app-blue|" + "a" * 64 + "|" + _runtime().image
    standby = "app-green|" + "b" * 64 + "|" + _runtime().image
    outputs = iter([
        workflow.RemoteOutput(0, primary),
        workflow.RemoteOutput(0, primary), workflow.RemoteOutput(0, ""),
        workflow.RemoteOutput(0, standby), workflow.RemoteOutput(0, ""),
        workflow.RemoteOutput(0, _rollback_payload()),
        workflow.RemoteOutput(0, primary), workflow.RemoteOutput(0, _verify_payload(mode="legacy")),
        workflow.RemoteOutput(0, standby), workflow.RemoteOutput(0, _verify_payload(mode="legacy")),
    ])
    monkeypatch.setattr(workflow, "create_context", lambda *args: object())
    monkeypatch.setattr(workflow, "validate_effective_config", lambda *args: None)
    monkeypatch.setattr(workflow, "discover_cluster_topology", lambda **kwargs: topology)
    monkeypatch.setattr(workflow, "_reviewed_backend_image_for_sha", lambda *args: _runtime().image)
    rollback_plan = _plan_payload()
    rollback_plan["current"] = {"auth_mode": "staff_shadow"}
    monkeypatch.setattr(
        workflow,
        "_fresh_plan",
        lambda *args, **kwargs: (rollback_plan, "signed-token"),
    )
    monkeypatch.setattr(workflow, "_run_remote", lambda *args, **kwargs: next(outputs))
    artifact = workflow.execute(args)
    assert set(artifact["proof"]) == {node.alias for node in PATRONI_NODES}
    assert json.loads(args.result_file.read_text(encoding="utf-8"))["proof"] == artifact["proof"]
    assert "runtime_binding" not in args.result_file.read_text(encoding="utf-8")


def test_pre_mutation_gate_checks_both_nodes_and_refuses_image_drift(monkeypatch):
    topology = ClusterTopology(
        primary=PATRONI_NODES[0], standby=PATRONI_NODES[1],
        system_identifier="1234567890123456789", timeline=1,
    )
    outputs = iter([
        workflow.RemoteOutput(0, "app-blue|" + "a" * 64 + "|" + _runtime().image),
        workflow.RemoteOutput(0, ""),
        workflow.RemoteOutput(0, "app-green|" + "b" * 64 + "|ghcr.io/mvnby/air-api/backend@sha256:" + "c" * 64),
    ])
    monkeypatch.setattr(workflow, "_run_remote", lambda *args, **kwargs: next(outputs))
    with pytest.raises(workflow.WorkflowError, match="image differs"):
        workflow._assert_dual_node_runtime_capability(
            object(), topology, expected_image=_runtime().image
        )
