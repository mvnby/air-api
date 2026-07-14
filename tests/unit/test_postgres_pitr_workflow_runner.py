import io
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from scripts.ha import run_postgres_pitr_workflow as workflow_runner
from scripts.ha.pitr_cluster_topology import ClusterTopology
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES


IDENTITY = b"""-----BEGIN OPENSSH PRIVATE KEY-----
dGVzdC1vbmx5
-----END OPENSSH PRIVATE KEY-----
"""


def _topology(*, primary_index: int = 0, timeline: int = 9) -> ClusterTopology:
    primary = PATRONI_NODES[primary_index]
    standby = PATRONI_NODES[1 - primary_index]
    return ClusterTopology(
        primary=primary,
        standby=standby,
        system_identifier="7491209876543210000",
        timeline=timeline,
    )


def test_remote_command_uses_only_the_installed_manual_runner():
    command = workflow_runner._remote_command(
        phase="restore-drill",
        topology=_topology(primary_index=1),
        operation_id="a" * 32,
        expected_release_sha256="f" * 64,
        backup_id="basebackup-20260714",
        target_time="2026-07-13T01:02:03Z",
    )

    assert command.startswith("exec /usr/local/sbin/mvn-postgres-pitr-manual-runner ")
    assert "--phase restore-drill" in command
    assert "--project-dir /opt/mvn-reserve" in command
    assert "--compose-file docker-compose.patroni.yml" in command
    assert f"--operation-id {'a' * 32}" in command
    assert f"--expected-release-sha256 {'f' * 64}" in command
    assert "--backup-id basebackup-20260714" in command
    assert "--target-time 2026-07-13T01:02:03Z" in command
    assert "/tmp/" not in command
    assert "scripts/ha/" not in command


def test_non_restore_phases_reject_historical_restore_overrides():
    with pytest.raises(workflow_runner.WorkflowError, match="valid only"):
        workflow_runner._remote_command(
            phase="verify",
            topology=_topology(),
            operation_id="b" * 32,
            expected_release_sha256="f" * 64,
            backup_id="old-backup",
            target_time="",
        )


def test_target_time_must_be_canonical_and_in_the_past():
    with pytest.raises(workflow_runner.WorkflowError, match="canonical UTC"):
        workflow_runner._validate_target_time("2026-07-13 01:02:03")
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    with pytest.raises(workflow_runner.WorkflowError, match="strictly in the past"):
        workflow_runner._validate_target_time(future)


def test_identity_transport_accepts_one_openssh_key_and_rejects_junk():
    assert workflow_runner._read_identity(io.BytesIO(IDENTITY)) == IDENTITY
    with pytest.raises(workflow_runner.WorkflowError, match="one OpenSSH"):
        workflow_runner._read_identity(io.BytesIO(b"not-a-private-key\n"))
    with pytest.raises(workflow_runner.WorkflowError, match="invalid"):
        workflow_runner._read_identity(io.BytesIO(IDENTITY + b"\0"))


def test_execute_uses_pinned_alias_proves_topology_twice_and_cleans_context(
    tmp_path, monkeypatch
):
    topology = _topology()
    proofs = []
    commands = []

    def discover(*, context, runner):
        proofs.append(context)
        return topology

    def runner(args, stdin=None):
        commands.append((list(args), stdin))
        return subprocess.CompletedProcess(list(args), 0, "guarded proof passed\n", "")

    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(workflow_runner, "discover_cluster_topology", discover)
    monkeypatch.setattr(workflow_runner, "validate_effective_config", lambda *_: None)
    monkeypatch.setattr(workflow_runner.secrets, "token_hex", lambda _: "c" * 32)
    monkeypatch.setattr(workflow_runner, "_expected_release_sha256", lambda _: "f" * 64)

    workflow_runner.execute(
        phase="verify",
        backup_id="",
        target_time="",
        identity_stream=io.BytesIO(IDENTITY),
        runner=runner,
    )

    assert len(proofs) == 2
    assert len(commands) == 1
    args, stdin = commands[0]
    assert stdin is None
    assert args[-2] == "mvn-api"
    assert "/usr/local/sbin/mvn-postgres-pitr-manual-runner" in args[-1]
    assert f"--operation-id {'c' * 32}" in args[-1]
    assert f"--expected-release-sha256 {'f' * 64}" in args[-1]
    assert "185.250.45.54" not in args
    assert not list(tmp_path.iterdir())


def test_execute_fails_if_topology_changes_and_still_cleans_context(
    tmp_path, monkeypatch
):
    topologies = iter((_topology(timeline=9), _topology(primary_index=1, timeline=10)))

    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(
        workflow_runner,
        "discover_cluster_topology",
        lambda **_: next(topologies),
    )
    monkeypatch.setattr(workflow_runner, "validate_effective_config", lambda *_: None)
    monkeypatch.setattr(workflow_runner.secrets, "token_hex", lambda _: "d" * 32)
    monkeypatch.setattr(workflow_runner, "_expected_release_sha256", lambda _: "f" * 64)

    with pytest.raises(workflow_runner.WorkflowError, match="topology changed"):
        workflow_runner.execute(
            phase="logical-restore-drill",
            backup_id="",
            target_time="",
            identity_stream=io.BytesIO(IDENTITY),
            runner=lambda args, stdin=None: subprocess.CompletedProcess(args, 0, "", ""),
        )

    assert not list(tmp_path.iterdir())


def test_execute_reproves_topology_after_a_remote_failure(tmp_path, monkeypatch):
    topology = _topology()
    proof_count = 0

    def discover(**_):
        nonlocal proof_count
        proof_count += 1
        return topology

    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(workflow_runner, "discover_cluster_topology", discover)
    monkeypatch.setattr(workflow_runner, "validate_effective_config", lambda *_: None)
    monkeypatch.setattr(workflow_runner.secrets, "token_hex", lambda _: "e" * 32)
    monkeypatch.setattr(workflow_runner, "_expected_release_sha256", lambda _: "f" * 64)

    with pytest.raises(workflow_runner.WorkflowError, match="status 75"):
        workflow_runner.execute(
            phase="verify",
            backup_id="",
            target_time="",
            identity_stream=io.BytesIO(IDENTITY),
            runner=lambda args, stdin=None: subprocess.CompletedProcess(
                args, 75, "", "operation lock busy\n"
            ),
        )

    assert proof_count == 2
    assert not list(tmp_path.iterdir())


def test_cli_rejects_unknown_or_cross_phase_arguments():
    with pytest.raises(SystemExit) as unknown:
        workflow_runner.parse_args(["--phase", "arbitrary"])
    assert unknown.value.code == 64
    with pytest.raises(SystemExit) as cross_phase:
        workflow_runner.parse_args(
            ["--phase", "logical-restore-drill", "--backup-id", "old"]
        )
    assert cross_phase.value.code == 64
