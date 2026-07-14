import argparse
import os
import sys
from pathlib import Path

import pytest

from scripts.ha import run_postgres_pitr_tool as tool


IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "a" * 64


def test_candidate_probe_uses_only_inherited_env_file_fd(monkeypatch):
    monkeypatch.setattr(
        tool,
        "_validate_helper",
        lambda _name: (Path("/usr/local/sbin/upload"), "/run/mvn-pitr-tools/upload.py"),
    )
    monkeypatch.setattr(tool, "_mount", lambda *_args, **_kwargs: ["--mount", "safe"])
    args = argparse.Namespace(
        phase="credential-probe",
        transaction_id="b" * 32,
        node="zakup",
    )

    command = tool._tool_command(
        args,
        IMAGE,
        operation_id="a" * 32,
        secrets_path=Path("/proc/self/fd/9"),
        secrets_already_validated=True,
    )

    env_index = command.index("--env-file")
    assert command[env_index + 1] == "/proc/self/fd/9"
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY" not in " ".join(command)
    assert "com.mvn.pitr.operation=" + "a" * 32 in command
    assert command[-8:] == [
        "python",
        "-I",
        "/run/mvn-pitr-tools/upload.py",
        "probe",
        "--transaction-id",
        "b" * 32,
        "--node",
    ] + ["zakup"]


@pytest.mark.skipif(
    sys.platform != "linux" or not hasattr(os, "memfd_create"),
    reason="sealed memfd transport is Linux-specific",
)
def test_candidate_secret_fd_requires_all_write_seals(monkeypatch):
    import fcntl

    descriptor = os.memfd_create(
        "pitr-test", flags=os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, b"candidate")
        monkeypatch.setattr(tool, "_parse_secrets", lambda payload: {"ok": payload})

        with pytest.raises(RuntimeError, match="not fully sealed"):
            tool._validate_candidate_secret_fd(f"/proc/self/fd/{descriptor}")

        fcntl.fcntl(
            descriptor,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_WRITE
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_SEAL,
        )
        assert (
            tool._validate_candidate_secret_fd(f"/proc/self/fd/{descriptor}")
            == descriptor
        )
    finally:
        os.close(descriptor)


def test_basebackup_upload_forwards_exact_lineage(monkeypatch):
    monkeypatch.setattr(
        tool,
        "_validate_helper",
        lambda _name: (Path("/usr/local/sbin/upload"), "/run/mvn-pitr-tools/upload.py"),
    )
    monkeypatch.setattr(tool, "_validate_directory", lambda path, **_kwargs: path)
    monkeypatch.setattr(tool, "_mount", lambda *_args, **_kwargs: ["--mount", "safe"])
    args = argparse.Namespace(
        phase="basebackup-upload",
        data_dir="/var/lib/mvn-postgres-pitr/basebackups/id",
        backup_id="20260713T120000Z",
        system_identifier="7612345678901234567",
        timeline="7",
        start_lsn="1/A000000",
        end_lsn="1/B000000",
        started_at="2026-07-13T12:00:00Z",
        completed_at="2026-07-13T12:02:00Z",
        source_node="mvn-api",
        dry_run=False,
    )

    command = tool._tool_command(
        args,
        IMAGE,
        operation_id="a" * 32,
        secrets_path=Path("/proc/self/fd/9"),
        secrets_already_validated=True,
    )

    assert command[command.index(IMAGE) + 1 :] == [
        "python",
        "-I",
        "/run/mvn-pitr-tools/upload.py",
        "basebackup",
        "--source-dir",
        "/pitr-data",
        "--backup-id",
        "20260713T120000Z",
        "--system-identifier",
        "7612345678901234567",
        "--timeline",
        "7",
        "--start-lsn",
        "1/A000000",
        "--end-lsn",
        "1/B000000",
        "--started-at",
        "2026-07-13T12:00:00Z",
        "--completed-at",
        "2026-07-13T12:02:00Z",
        "--source-node",
        "mvn-api",
    ]


def test_remote_status_forwards_exact_cluster_identity(monkeypatch):
    monkeypatch.setattr(
        tool,
        "_validate_helper",
        lambda name: (
            Path(f"/usr/local/sbin/{name}"),
            f"/run/mvn-pitr-tools/{name}.py",
        ),
    )
    monkeypatch.setattr(tool, "_mount", lambda *_args, **_kwargs: ["--mount", "safe"])
    args = argparse.Namespace(
        phase="remote-status",
        max_wal_age_minutes="180",
        max_basebackup_age_hours="30",
        local_pending_wal_count=0,
        expected_wal="00000007000000010000000A",
        expected_system_identifier="7612345678901234567",
    )

    command = tool._tool_command(
        args,
        IMAGE,
        operation_id="a" * 32,
        secrets_path=Path("/proc/self/fd/9"),
        secrets_already_validated=True,
    )

    assert command[-4:] == [
        "--expected-system-identifier",
        "7612345678901234567",
        "--expected-wal",
        "00000007000000010000000A",
    ]


def test_restore_prepare_forwards_lineage_and_contiguous_wal_bound(monkeypatch):
    monkeypatch.setattr(
        tool,
        "_validate_helper",
        lambda name: (
            Path(f"/usr/local/sbin/{name}"),
            f"/run/mvn-pitr-tools/{name}.py",
        ),
    )
    monkeypatch.setattr(tool, "_validate_directory", lambda path, **_kwargs: path)
    monkeypatch.setattr(tool, "_mount", lambda *_args, **_kwargs: ["--mount", "safe"])
    args = argparse.Namespace(
        phase="restore-prepare",
        data_dir="/var/lib/mvn-postgres-pitr/restore-drills/id/restore",
        backup_id="20260713T120000Z",
        target_time="2026-07-13T12:10:00Z",
        target_name="",
        target_lsn="",
        expected_system_identifier="7612345678901234567",
        required_end_wal="00000007000000010000000A",
    )

    command = tool._tool_command(
        args,
        IMAGE,
        operation_id="a" * 32,
        secrets_path=Path("/proc/self/fd/9"),
        secrets_already_validated=True,
    )

    tool_args = command[command.index(IMAGE) + 1 :]
    assert tool_args[tool_args.index("--expected-system-identifier") + 1] == (
        "7612345678901234567"
    )
    assert tool_args[tool_args.index("--required-end-wal") + 1] == (
        "00000007000000010000000A"
    )
    assert tool_args[tool_args.index("--target-time") + 1] == (
        "2026-07-13T12:10:00Z"
    )


def test_restore_prepare_forwards_named_restore_point_and_exact_lsn(monkeypatch):
    monkeypatch.setattr(
        tool,
        "_validate_helper",
        lambda name: (Path(f"/{name}"), f"/run/{name}.py"),
    )
    monkeypatch.setattr(tool, "_validate_directory", lambda path, **_kwargs: path)
    monkeypatch.setattr(tool, "_mount", lambda *_args, **_kwargs: ["--mount", "safe"])
    args = argparse.Namespace(
        phase="restore-prepare",
        data_dir="/var/lib/mvn-postgres-pitr/restore-drills/id/restore",
        backup_id="",
        target_time="",
        target_name="mvn_pitr_" + "b" * 32,
        target_lsn="1/B000000",
        expected_system_identifier="7612345678901234567",
        required_end_wal="00000007000000010000000A",
    )

    command = tool._tool_command(
        args,
        IMAGE,
        operation_id="a" * 32,
        secrets_path=Path("/proc/self/fd/9"),
        secrets_already_validated=True,
    )

    tool_args = command[command.index(IMAGE) + 1 :]
    assert tool_args[tool_args.index("--target-name") + 1] == args.target_name
    assert tool_args[tool_args.index("--target-lsn") + 1] == "1/B000000"


def test_wal_upload_runs_as_exact_validated_archive_owner(monkeypatch):
    monkeypatch.setattr(
        tool,
        "_validate_helper",
        lambda _name: (Path("/upload"), "/run/upload.py"),
    )
    monkeypatch.setattr(
        tool,
        "_validate_archive_directory",
        lambda path: (path, 70, 70),
    )
    monkeypatch.setattr(tool, "_mount", lambda *_args, **_kwargs: ["--mount", "safe"])
    args = argparse.Namespace(
        phase="wal-upload",
        data_dir="/opt/air-api/postgres-wal-archive",
        dry_run=False,
        delete_after_upload=True,
    )

    command = tool._tool_command(
        args,
        IMAGE,
        operation_id="a" * 32,
        secrets_path=Path("/proc/self/fd/9"),
        secrets_already_validated=True,
    )

    user_index = command.index("--user")
    assert command[user_index + 1] == "70:70"
    assert user_index < command.index(IMAGE)


def test_archive_directory_requires_exact_owner_modes_and_wal_size(
    monkeypatch,
    tmp_path,
):
    archive = tmp_path / "archive"
    archive.mkdir(mode=0o700)
    wal = archive / "000000010000000000000001"
    with wal.open("wb") as stream:
        stream.truncate(16 * 1024 * 1024)
    wal.chmod(0o600)
    monkeypatch.setattr(tool, "ARCHIVE_UID", os.getuid())
    monkeypatch.setattr(tool, "ARCHIVE_GID", os.getgid())
    monkeypatch.setattr(tool, "_validate_directory", lambda path, **_kwargs: path)

    assert tool._validate_archive_directory(archive) == (
        archive,
        os.getuid(),
        os.getgid(),
    )

    wal.chmod(0o644)
    with pytest.raises(RuntimeError, match="entry ownership or mode"):
        tool._validate_archive_directory(archive)


@pytest.mark.parametrize(
    ("size", "accepted"),
    [
        (16 * 1024 * 1024, True),
        (16 * 1024 * 1024 - 1, False),
        (16 * 1024 * 1024 + 1, False),
    ],
)
def test_archive_directory_validates_promotion_partial_size(
    monkeypatch, tmp_path, size, accepted
):
    archive = tmp_path / "archive"
    archive.mkdir(mode=0o700)
    partial = archive / "00000007000000000000004B.partial"
    with partial.open("wb") as stream:
        stream.truncate(size)
    partial.chmod(0o600)
    lock = archive / ".mvn-pitr-archive.lock"
    lock.touch(mode=0o600)
    monkeypatch.setattr(tool, "ARCHIVE_UID", os.getuid())
    monkeypatch.setattr(tool, "ARCHIVE_GID", os.getgid())
    monkeypatch.setattr(tool, "_validate_directory", lambda path, **_kwargs: path)

    if accepted:
        assert tool._validate_archive_directory(archive)[0] == archive
    else:
        with pytest.raises(RuntimeError, match="WAL segment size is invalid"):
            tool._validate_archive_directory(archive)
