#!/usr/bin/env python3
"""Generate a known-safe PostgreSQL recovery config outside restored PGDATA."""

from __future__ import annotations

import os
import shlex
import stat
from datetime import datetime
from pathlib import Path


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _create_recovery_signal(data_dir: Path) -> None:
    signal_path = data_dir / "recovery.signal"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(signal_path, flags, 0o600)
    os.close(descriptor)


def write_recovery_settings(
    *,
    data_dir: Path,
    control_dir: Path,
    target_time: datetime | None,
    target_name: str,
    wal_mode: str,
    restore_mount_path: str,
    restore_helper_path: str,
) -> None:
    data_root = data_dir.resolve()
    control_root = control_dir.resolve()
    if control_root.parent != data_root.parent or control_root == data_root:
        raise SystemExit("PITR recovery control directory is outside the restore root")
    control_dir.mkdir(mode=0o700)
    metadata = control_dir.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_gid != os.getegid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise SystemExit("PITR recovery control directory metadata is unsafe")
    if wal_mode == "local":
        # The drill mounts its verified WAL source read-only and deliberately
        # keeps archive members at 0400.  Plain ``cp`` carries that mode to
        # PostgreSQL's RECOVERYHISTORY staging file, which PostgreSQL must
        # subsequently reopen for writing.  Install the destination with the
        # normal server-owned 0600 mode while leaving the archive immutable.
        restore_command = (
            "/usr/bin/install -m 0600 "
            f"{shlex.quote(restore_mount_path.rstrip('/') + '/wal/%f')} %p"
        )
    elif wal_mode == "remote":
        restore_command = (
            f"python3 {shlex.quote(restore_helper_path)} "
            "fetch-wal --wal-name %f --destination %p"
        )
    else:
        raise ValueError(f"Unsupported wal_mode={wal_mode!r}")
    target_value = target_time.isoformat() if target_time else target_name
    target_parameter = "recovery_target_time" if target_time else "recovery_target_name"
    settings = [
        "# Generated MVN PITR config; restored settings are ignored.",
        f"restore_command = {_quote(restore_command)}",
        "recovery_target_action = 'pause'",
        f"recovery_target_inclusive = {'off' if target_time else 'on'}",
        f"{target_parameter} = {_quote(target_value)}",
        "archive_cleanup_command = ''",
        "archive_command = ''",
        "archive_library = ''",
        "archive_mode = off",
        "dynamic_library_path = ''",
        "jit = off",
        "local_preload_libraries = ''",
        "primary_conninfo = ''",
        "primary_slot_name = ''",
        "recovery_end_command = ''",
        "session_preload_libraries = ''",
        "shared_preload_libraries = ''",
        "ssl = off",
        "ssl_passphrase_command = ''",
    ]
    config_path = control_dir / "postgresql.conf"
    with config_path.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(settings) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(config_path, 0o600)
    _create_recovery_signal(data_dir)
