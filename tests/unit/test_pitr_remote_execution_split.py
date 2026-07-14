import ast
import hashlib
import json
import os
import shlex
import subprocess
import sys

import pytest

from scripts.ha import pitr_remote_execution, pitr_remote_executors
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES, PinnedSshContext


EXECUTORS = (
    pitr_remote_executors.REMOTE_SECRET_EXECUTOR,
    pitr_remote_executors.REMOTE_MAINTENANCE_EXECUTOR,
    pitr_remote_executors.REMOTE_ROLE_AGENT_EXECUTOR,
    pitr_remote_executors.LOCKED_MAINTENANCE_WRAPPER,
)


def _context(tmp_path):
    return PinnedSshContext(
        identity_file=tmp_path / "identity",
        known_hosts_file=tmp_path / "known-hosts",
        config_file=tmp_path / "ssh-config",
    )


@pytest.mark.parametrize("source", EXECUTORS)
def test_embedded_executor_is_valid_isolated_python(source):
    ast.parse(source)
    compile(source, "<pitr-remote-executor>", "exec")

    result = subprocess.run(
        [sys.executable, "-I", "-c", source],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 64
    assert "invalid invocation" in result.stderr


def test_attestation_loader_uses_an_absolute_path_under_isolated_python(tmp_path):
    guard = tmp_path / "operation_guard.py"
    guard.write_text("LOADED_FROM_ABSOLUTE_PATH = True\n", encoding="utf-8")
    program = (
        pitr_remote_executors.REMOTE_ASSET_ATTESTATION
        + "\nOPERATION_GUARD_PATH = sys.argv[1]"
        + "\nassert os.path.isabs(OPERATION_GUARD_PATH)"
        + "\nassert load_operation_guard().LOADED_FROM_ABSOLUTE_PATH is True"
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", program, str(guard.resolve())],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_execution_module_preserves_executor_exports():
    assert (
        pitr_remote_execution.REMOTE_ASSET_ATTESTATION
        is pitr_remote_executors.REMOTE_ASSET_ATTESTATION
    )
    assert (
        pitr_remote_execution.REMOTE_SECRET_EXECUTOR
        is pitr_remote_executors.REMOTE_SECRET_EXECUTOR
    )
    assert (
        pitr_remote_execution.REMOTE_MAINTENANCE_EXECUTOR
        is pitr_remote_executors.REMOTE_MAINTENANCE_EXECUTOR
    )
    assert (
        pitr_remote_execution.REMOTE_ROLE_AGENT_EXECUTOR
        is pitr_remote_executors.REMOTE_ROLE_AGENT_EXECUTOR
    )
    assert (
        pitr_remote_execution.LOCKED_MAINTENANCE_WRAPPER
        is pitr_remote_executors.LOCKED_MAINTENANCE_WRAPPER
    )


def test_secret_remote_command_contains_exact_embedded_program(tmp_path):
    captured = []

    def runner(args, stdin):
        captured.append((list(args), stdin))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    pitr_remote_execution.run_remote_secret_phase(
        node=PATRONI_NODES[0],
        context=_context(tmp_path),
        env_text="secret-payload",
        bootstrap_helper="/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        phase="configure-node",
        transaction_id="0123456789abcdef0123456789abcdef",
        runner=runner,
    )

    args, stdin = captured[0]
    command = shlex.split(args[-1])
    assert command[:3] == ["/usr/bin/python3", "-I", "-c"]
    assert command[3] == pitr_remote_executors.REMOTE_SECRET_EXECUTOR
    assert command[4:9] == [
        "/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        "configure-node",
        "/opt/air-api",
        "docker-compose.patroni.yml",
        "0123456789abcdef0123456789abcdef",
    ]
    manifest = json.loads(command[9])
    assert manifest["/usr/local/sbin/mvn_postgres_pitr_config_transaction.py"]
    assert command[10] == pitr_remote_executors.LOCKED_MAINTENANCE_WRAPPER
    assert command[11] == hashlib.sha256(command[10].encode()).hexdigest()
    assert stdin == "secret-payload"


def test_secret_executor_uses_transient_cgroup_and_pipe_only_transport():
    source = pitr_remote_executors.REMOTE_SECRET_EXECUTOR

    assert "transient=True" in source
    assert "stdin_payload=payload_view" in source
    assert "ENV_INPUT_FILE" not in source.split("def main():", 1)[1]
    assert "os.memfd_create" in pitr_remote_executors.LOCKED_MAINTENANCE_WRAPPER
    assert 'environment["ENV_INPUT_FILE"]' in (
        pitr_remote_executors.LOCKED_MAINTENANCE_WRAPPER
    )
    assert '"PITR_TRANSACTION_ID": transaction_id' in (
        pitr_remote_executors.LOCKED_MAINTENANCE_WRAPPER
    )
    assert "operation_id=transaction_id" in source
    assert 're.fullmatch(r"[0-9a-f]{32}", transaction_id)' in source
    assert 're.fullmatch(r"[0-9a-f]{32}", transaction_id)' in (
        pitr_remote_executors.LOCKED_MAINTENANCE_WRAPPER
    )


def test_maintenance_remote_command_contains_exact_nested_programs(tmp_path):
    captured = []

    def runner(args, stdin):
        captured.append((list(args), stdin))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    pitr_remote_execution.run_remote_maintenance_phase(
        node=PATRONI_NODES[1],
        context=_context(tmp_path),
        bootstrap_helper="/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        phase="verify",
        transaction_id="0123456789abcdef0123456789abcdef",
        runner=runner,
    )

    args, stdin = captured[0]
    command = shlex.split(args[-1])
    assert command[:3] == ["/usr/bin/python3", "-I", "-c"]
    assert command[3] == pitr_remote_executors.REMOTE_MAINTENANCE_EXECUTOR
    assert command[4:10] == [
        "/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        "verify",
        "/opt/mvn-reserve",
        "docker-compose.patroni.yml",
        "false",
        "0123456789abcdef0123456789abcdef",
    ]
    json.loads(command[10])
    assert command[11] == pitr_remote_executors.LOCKED_MAINTENANCE_WRAPPER
    assert command[12] == hashlib.sha256(command[11].encode()).hexdigest()
    assert stdin is None
    assert 're.fullmatch(r"[0-9a-f]{32}", transaction_id)' in (
        pitr_remote_executors.REMOTE_MAINTENANCE_EXECUTOR
    )
    assert "operation_id=transaction_id" in (
        pitr_remote_executors.REMOTE_MAINTENANCE_EXECUTOR
    )


def test_transactional_host_provision_is_an_attested_maintenance_phase(tmp_path):
    captured = []

    def runner(args, stdin):
        captured.append((list(args), stdin))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    pitr_remote_execution.run_remote_maintenance_phase(
        node=PATRONI_NODES[0],
        context=_context(tmp_path),
        bootstrap_helper="/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        phase="provision-node",
        transaction_id="0123456789abcdef0123456789abcdef",
        runner=runner,
    )

    command = shlex.split(captured[0][0][-1])
    assert command[5] == "provision-node"
    assert '"provision-node": 900' in pitr_remote_executors.REMOTE_MAINTENANCE_EXECUTOR
    assert '"provision-node"' in pitr_remote_executors.LOCKED_MAINTENANCE_WRAPPER


def test_role_agent_remote_command_is_pinned_and_attests_exact_assets(tmp_path):
    captured = []

    def runner(args, stdin):
        captured.append((list(args), stdin))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    pitr_remote_execution.run_remote_role_agent_phase(
        node=PATRONI_NODES[1],
        context=_context(tmp_path),
        phase="quiesce-standby",
        transaction_id="0123456789abcdef0123456789abcdef",
        runner=runner,
    )

    args, stdin = captured[0]
    command = shlex.split(args[-1])
    assert command[:3] == ["/usr/bin/python3", "-I", "-c"]
    assert command[3] == pitr_remote_executors.REMOTE_ROLE_AGENT_EXECUTOR
    assert command[4:7] == [
        "quiesce-standby",
        "/opt/mvn-reserve",
        "0123456789abcdef0123456789abcdef",
    ]
    manifest = json.loads(command[7])
    assert set(manifest) == {
        "/usr/local/sbin/mvn-patroni-role-agent",
        "/usr/local/sbin/patroni_local_identity.py",
        "/etc/systemd/system/mvn-patroni-role-agent.service",
        "/usr/local/sbin/mvn_postgres_pitr_operation_guard.py",
        "/usr/local/sbin/mvn_postgres_pitr_operation_cleanup.py",
    }
    assert all(len(digest) == 64 for digest in manifest.values())
    assert stdin is None


def test_role_agent_executor_keeps_quiesce_fenced_and_resume_fail_closed():
    source = pitr_remote_executors.REMOTE_ROLE_AGENT_EXECUTOR

    assert 'require_fence(project_dir, transaction_id, allow_finalized=False)' in source
    assert '["/usr/bin/systemctl", "disable", ROLE_AGENT_UNIT]' in source
    assert 'unit_state("is-active") != "inactive"' in source
    assert 'unit_state("is-enabled") != "disabled"' in source
    assert "role_agent._fence_lost_primary(config)" in source
    assert "guard.cancel_project_operations(project_dir)" in source
    assert "execute_attested_module" in source
    assert "sources[OPERATION_GUARD_PATH]" in source
    assert 'attest_live_process(expected_environment, manifest)' in source
    assert "open_deploy_lock_bounded(project_dir)" in source
    assert "wait_for_convergence(role_agent, config, expected_role)" in source


def _role_executor_namespace():
    source = pitr_remote_executors.REMOTE_ROLE_AGENT_EXECUTOR
    prefix = source.rsplit("raise SystemExit(main())", 1)[0]
    namespace = {"__name__": "pitr_role_executor_behavior"}
    exec(compile(prefix, "<pitr-role-executor>", "exec"), namespace)
    return namespace


def test_record_drain_waits_then_reaps_and_cancels_via_attested_guard():
    namespace = _role_executor_namespace()
    events = []
    record = type("Record", (), {"operation_id": "0" * 32})()

    class Guard:
        records = [record]

        def list_records(self, **_kwargs):
            events.append("list")
            return list(self.records)

        def reconcile_project_operations(self, _project):
            events.append("reconcile")
            if self.records:
                raise RuntimeError("active")

        def cancel_project_operations(self, _project):
            events.append("cancel")
            self.records.clear()

    namespace["drain_operations"](
        "/opt/air-api", "0" * 32, Guard(), wait_seconds=0
    )

    assert events == [
        "list", "list", "reconcile", "cancel", "reconcile", "list"
    ]


def test_record_drain_never_reaps_or_cancels_a_foreign_transaction():
    namespace = _role_executor_namespace()
    events = []
    record = type("Record", (), {"operation_id": "f" * 32})()

    class Guard:
        def list_records(self, **_kwargs):
            events.append("list")
            return [record]

        def reconcile_project_operations(self, _project):
            events.append("reconcile")

        def cancel_project_operations(self, _project):
            events.append("cancel")

    with pytest.raises(RuntimeError, match="foreign PITR operation"):
        namespace["drain_operations"](
            "/opt/air-api", "0" * 32, Guard(), wait_seconds=0
        )

    assert events == ["list", "list"]


def test_primary_quiesce_behavior_fences_before_disabling_main_agent():
    namespace = _role_executor_namespace()
    events = []
    state = {"active": "active", "enabled": "enabled"}

    class Guard:
        def reconcile_project_operations(self, _project):
            events.append("reconcile-under-lock")

    class RoleAgent:
        def _fence_lost_primary(self, _config):
            events.append("fence-runtime")

    contract = (
        {"asset": "digest"},
        {"HA_PROJECT_DIR": "/opt/air-api"},
        Guard(),
        RoleAgent(),
        object(),
    )
    namespace["attest_contract"] = lambda *_args: (
        events.append("attest") or contract
    )
    namespace["drain_operations"] = lambda *_args, **_kwargs: events.append(
        "drain"
    )
    namespace["require_fence"] = lambda *_args, **_kwargs: (
        events.append("fence-proof") or "maintenance"
    )
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)
    namespace["open_deploy_lock_bounded"] = lambda *_args, **_kwargs: os.open(
        os.devnull, os.O_RDONLY
    )
    namespace["attest_live_process"] = lambda *_args: events.append("live-proof")
    namespace["prove_safe_state"] = lambda *_args, **kwargs: events.append(
        "safe-" + kwargs["required"]
    )
    namespace["unit_state"] = lambda kind: state[
        "active" if kind == "is-active" else "enabled"
    ]

    def checked(args, **_kwargs):
        action = args[1]
        events.append(action)
        if action == "disable":
            state["enabled"] = "disabled"
        elif action == "stop":
            state["active"] = "inactive"
        return ""

    namespace["checked"] = checked
    namespace["quiesce"](
        "quiesce-fenced", "/opt/air-api", "0" * 32, "manifest"
    )

    assert events.index("fence-runtime") < events.index("disable")
    assert events.index("safe-fenced") < events.index("disable")
    assert events.count("attest") == 2
    assert events.count("drain") == 2


def test_quiesce_foreign_record_race_fails_before_disabling_agent():
    namespace = _role_executor_namespace()
    events = []
    contract = ({}, {}, object(), object(), object())
    namespace["attest_contract"] = lambda *_args: contract
    namespace["require_fence"] = lambda *_args, **_kwargs: "maintenance"
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)
    namespace["open_deploy_lock_bounded"] = lambda *_args, **_kwargs: os.open(
        os.devnull, os.O_RDONLY
    )
    calls = 0

    def drain(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        events.append("drain")
        if calls == 2:
            raise RuntimeError("foreign PITR operation records remain")

    namespace["drain_operations"] = drain
    namespace["checked"] = lambda *_args, **_kwargs: events.append("systemctl")

    with pytest.raises(RuntimeError, match="foreign PITR operation"):
        namespace["quiesce"](
            "quiesce-standby", "/opt/air-api", "0" * 32, "manifest"
        )

    assert events == ["drain", "drain"]


def test_resume_behavior_holds_lock_for_start_then_reacquires_for_final_proof():
    namespace = _role_executor_namespace()
    events = []
    state = {"active": "inactive", "enabled": "disabled"}

    class Guard:
        def reconcile_project_operations(self, _project):
            events.append("reconcile-under-lock")

    contract = (
        {"asset": "digest"},
        {"HA_PROJECT_DIR": "/opt/air-api"},
        Guard(),
        object(),
        object(),
    )
    namespace["attest_contract"] = lambda *_args: (
        events.append("attest") or contract
    )
    namespace["drain_operations"] = lambda *_args, **_kwargs: events.append(
        "drain"
    )
    namespace["require_fence"] = lambda *_args, **_kwargs: (
        events.append("fence-proof") or "maintenance"
    )
    namespace["open_global_lock"] = lambda: os.open(os.devnull, os.O_RDONLY)

    def deploy_lock(*_args, **_kwargs):
        events.append("deploy-lock")
        return os.open(os.devnull, os.O_RDONLY)

    namespace["open_deploy_lock_bounded"] = deploy_lock
    namespace["attest_live_process"] = lambda *_args: events.append("live-proof")
    namespace["wait_for_convergence"] = lambda *_args: events.append("converged")
    namespace["prove_safe_state"] = lambda *_args, **_kwargs: events.append("safe-live")
    namespace["unit_state"] = lambda kind: state[
        "active" if kind == "is-active" else "enabled"
    ]

    def checked(args, **_kwargs):
        action = args[1]
        events.append(action)
        if action == "enable":
            state["enabled"] = "enabled"
        elif action == "start":
            state["active"] = "active"
        return ""

    namespace["checked"] = checked
    namespace["resume"](
        "/opt/air-api", "0" * 32, "manifest", "primary"
    )

    assert events.count("deploy-lock") == 2
    assert events.index("start") < events.index("converged")
    assert events.index("converged") < events.index("safe-live")
    assert events.count("attest") == 3


def test_primary_convergence_never_accepts_unavailable_local_role_proof():
    namespace = _role_executor_namespace()

    class RoleAgent:
        def _fetch_configured_patroni_role(self, _config):
            raise RuntimeError("local Patroni proof unavailable")

    with pytest.raises(RuntimeError, match="local Patroni proof unavailable"):
        namespace["prove_safe_state"](
            RoleAgent(),
            object(),
            required="live",
            expected_role="primary",
        )


@pytest.mark.parametrize(
    "transaction_id",
    ["", "A" * 32, "0" * 31, "0" * 33, "g" * 32, "../../unsafe"],
)
def test_remote_phases_reject_noncanonical_transaction_id(tmp_path, transaction_id):
    common = {
        "node": PATRONI_NODES[0],
        "context": _context(tmp_path),
        "bootstrap_helper": "/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        "transaction_id": transaction_id,
    }
    with pytest.raises(RuntimeError, match="transaction ID"):
        pitr_remote_execution.run_remote_secret_phase(
            **common,
            env_text="secret-payload",
            phase="preflight",
        )
    with pytest.raises(RuntimeError, match="transaction ID"):
        pitr_remote_execution.run_remote_maintenance_phase(
            **common,
            phase="verify",
        )
    with pytest.raises(RuntimeError, match="transaction ID"):
        pitr_remote_execution.run_remote_role_agent_phase(
            node=common["node"],
            context=common["context"],
            phase="resume-primary",
            transaction_id=transaction_id,
        )
