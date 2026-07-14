import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import pitr_operation_guard as guard
from scripts.ha import pitr_operation_cleanup as cleanup


def _record() -> guard.OperationRecord:
    return guard.OperationRecord(
        operation_id="a" * 32,
        kind="manual",
        phase="configure-node",
        project_dir="/opt/air-api",
        pid=123,
        pgid=123,
        start_time="456",
        command="/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        unit="mvn-postgres-pitr-manual-" + "a" * 32 + ".service",
    )


def test_cloexec_pipe_falls_back_portably(monkeypatch):
    real_pipe = os.pipe
    monkeypatch.delattr(guard.os, "pipe2", raising=False)
    monkeypatch.setattr(guard.os, "pipe", real_pipe)

    read_fd, write_fd = guard._cloexec_pipe()
    try:
        assert os.get_inheritable(read_fd) is False
        assert os.get_inheritable(write_fd) is False
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_remove_record_is_idempotent_when_concurrent_remover_wins_before_lstat(
    monkeypatch,
):
    record = _record()
    monkeypatch.setattr(guard, "_read_record", lambda _path: (record, (1, 2)))

    def missing(_path):
        raise FileNotFoundError

    monkeypatch.setattr(Path, "lstat", missing)

    guard.remove_record(record, missing_ok=True)


def test_remove_record_is_idempotent_when_concurrent_remover_wins_before_unlink(
    monkeypatch,
):
    record = _record()
    monkeypatch.setattr(guard, "_read_record", lambda _path: (record, (1, 2)))
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda _path: SimpleNamespace(st_dev=1, st_ino=2),
    )

    def missing(_path):
        raise FileNotFoundError

    monkeypatch.setattr(Path, "unlink", missing)

    guard.remove_record(record, missing_ok=True)


def test_parent_bound_launcher_rejects_an_unrelated_expected_parent():
    read_fd, write_fd = os.pipe()
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                guard.PARENT_BOUND_LAUNCHER,
                str(os.getpid() + 100000),
                str(read_fd),
                "/usr/bin/true",
            ],
            pass_fds=(read_fd,),
            check=False,
        )
    finally:
        os.close(read_fd)
        os.close(write_fd)

    assert result.returncode == 125


def test_operation_cleanup_removes_only_exact_attested_logical_volume(monkeypatch):
    operation_id = "c" * 32
    volume = f"mvn-logical-restore-{operation_id}-data"
    volume_lists = iter([volume + "\n", ""])
    commands = []

    def fake_run(args, *, timeout=30):
        commands.append(list(args))
        if args[:4] == ["docker", "volume", "ls", "-q"]:
            return subprocess.CompletedProcess(args, 0, next(volume_lists), "")
        if args[:4] == ["docker", "volume", "inspect", "--format"]:
            labels = {
                "com.mvn.pitr.operation": operation_id,
                "com.mvn.purpose": "api-restore-drill",
            }
            return subprocess.CompletedProcess(args, 0, __import__("json").dumps(labels), "")
        if args[:3] == ["docker", "volume", "rm"]:
            return subprocess.CompletedProcess(args, 0, volume + "\n", "")
        raise AssertionError(args)

    monkeypatch.setattr(cleanup, "_run", fake_run)
    cleanup._cleanup_volumes(operation_id)

    assert ["docker", "volume", "rm", volume] in commands


def test_operation_cleanup_rejects_a_labelled_volume_with_unexpected_name(monkeypatch):
    operation_id = "d" * 32
    removed = []

    def fake_run(args, *, timeout=30):
        if args[:4] == ["docker", "volume", "ls", "-q"]:
            return subprocess.CompletedProcess(args, 0, "unrelated\n", "")
        if args[:3] == ["docker", "volume", "rm"]:
            removed.append(args[-1])
        raise AssertionError(args)

    monkeypatch.setattr(cleanup, "_run", fake_run)
    with pytest.raises(RuntimeError, match="volume set is invalid"):
        cleanup._cleanup_volumes(operation_id)

    assert removed == []


def test_operation_cleanup_rejects_labelled_container_with_unreviewed_name(monkeypatch):
    operation_id = "d" * 32
    identifier = "e" * 64
    removed = []

    def fake_run(args, *, timeout=30):
        if args[:3] == ["docker", "ps", "-aq"]:
            return subprocess.CompletedProcess(args, 0, identifier + "\n", "")
        if args[:4] == ["docker", "inspect", "--format", "{{json .Name}}"]:
            return subprocess.CompletedProcess(args, 0, '"/unreviewed"\n', "")
        if args[:4] == ["docker", "inspect", "--format", "{{json .Config.Labels}}"]:
            return subprocess.CompletedProcess(
                args,
                0,
                __import__("json").dumps({"com.mvn.pitr.operation": operation_id}),
                "",
            )
        if args[:3] == ["docker", "rm", "-f"]:
            removed.append(args[-1])
        raise AssertionError(args)

    monkeypatch.setattr(cleanup, "_run", fake_run)
    with pytest.raises(RuntimeError, match="container set is invalid"):
        cleanup._cleanup_containers(operation_id)

    assert removed == []


def test_reconcile_project_cleans_proven_dead_record_and_orphan_state(monkeypatch):
    record = _record()
    listings = iter([[record], []])
    cleaned = []
    removed = []
    monkeypatch.setattr(guard, "list_records", lambda **_kwargs: next(listings))
    monkeypatch.setattr(guard, "_pid_matches", lambda _record: False)
    monkeypatch.setattr(guard, "_process_group_alive", lambda _pgid: False)
    monkeypatch.setattr(guard, "_unit_active", lambda _unit: False)
    monkeypatch.setattr(guard, "cleanup_operation_artifacts", cleaned.append)
    monkeypatch.setattr(
        guard, "remove_record", lambda item, **_kwargs: removed.append(item.operation_id)
    )
    monkeypatch.setattr(
        guard, "reconcile_orphan_artifacts", lambda _protected: ["e" * 32]
    )

    result = guard.reconcile_project_operations("/opt/air-api")

    assert result == [record.operation_id, "e" * 32]
    assert cleaned == [record.operation_id]
    assert removed == [record.operation_id]


def test_reconcile_project_refuses_active_or_ambiguous_record(monkeypatch):
    record = _record()
    monkeypatch.setattr(guard, "list_records", lambda **_kwargs: [record])
    monkeypatch.setattr(guard, "_pid_matches", lambda _record: True)
    monkeypatch.setattr(guard, "_process_group_alive", lambda _pgid: True)
    monkeypatch.setattr(guard, "_unit_active", lambda _unit: True)

    with pytest.raises(RuntimeError, match="active PITR operation"):
        guard.reconcile_project_operations("/opt/air-api")


@pytest.mark.skipif(sys.platform != "linux", reason="PDEATHSIG is Linux-specific")
@pytest.mark.parametrize("release_barrier", [False, True])
def test_parent_death_never_leaves_the_guarded_payload_running(
    tmp_path, release_barrier
):
    marker = tmp_path / "payload-ran"
    supervisor = r'''
import os
import subprocess
import sys

launcher, marker, release = sys.argv[1:]
read_fd, write_fd = os.pipe()
payload = (
    "import pathlib,sys,time; time.sleep(1); "
    "pathlib.Path(sys.argv[1]).write_text('ran', encoding='utf-8')"
)
subprocess.Popen(
    [
        sys.executable,
        "-I",
        "-c",
        launcher,
        str(os.getpid()),
        str(read_fd),
        sys.executable,
        "-I",
        "-c",
        payload,
        marker,
    ],
    pass_fds=(read_fd,),
    start_new_session=True,
)
os.close(read_fd)
if release == "yes":
    os.write(write_fd, b"1")
os.close(write_fd)
'''
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            supervisor,
            guard.PARENT_BOUND_LAUNCHER,
            str(marker),
            "yes" if release_barrier else "no",
        ],
        check=False,
    )
    assert result.returncode == 0
    time.sleep(1.3)
    assert not marker.exists()


@pytest.mark.skipif(sys.platform != "linux", reason="operation records use Linux /proc")
def test_guarded_process_streams_stdin_only_after_its_record_exists(
    tmp_path, monkeypatch
):
    record_root = tmp_path / "records"
    output = tmp_path / "stdin"
    monkeypatch.setattr(guard, "RECORD_ROOT", record_root)
    monkeypatch.setattr(guard, "cleanup_operation_artifacts", lambda _operation_id: None)

    result = guard.run_guarded_process(
        ["/bin/sh", "-c", f"cat > {shlex.quote(str(output))}"],
        environment=dict(guard.CLEAN_ENV),
        phase="configure-node",
        project_dir="/opt/air-api",
        kind="manual",
        unit="",
        record_command="/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        timeout_seconds=10,
        stdin_payload=b"root-only-secret\n",
        operation_id="b" * 32,
    )

    assert result == 0
    assert output.read_bytes() == b"root-only-secret\n"
    assert not list(record_root.glob("*.json"))
