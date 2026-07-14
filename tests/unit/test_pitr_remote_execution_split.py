import ast
import hashlib
import json
import shlex
import subprocess
import sys

import pytest

from scripts.ha import pitr_remote_execution, pitr_remote_executors
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES, PinnedSshContext


EXECUTORS = (
    pitr_remote_executors.REMOTE_SECRET_EXECUTOR,
    pitr_remote_executors.REMOTE_MAINTENANCE_EXECUTOR,
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
