#!/usr/bin/env python3
"""Attest the canonical PITR maintenance marker for an internal scrub."""

from __future__ import annotations

import os
import re
import stat
import sys


MARKER_PATH = "/run/mvn-postgres-pitr-maintenance"
TRANSACTION_RE = re.compile(r"[0-9a-f]{32}")
PINNED_ROOT = "/usr/local/libexec/mvn-pitr"
PINNED_VALIDATOR = f"{PINNED_ROOT}/verify_pitr_maintenance_marker.py"
PINNED_RUNTIME_PATHS = (
    f"{PINNED_ROOT}/deploy_backend_blue_green.sh",
    f"{PINNED_ROOT}/safe_deploy_lock.py",
    f"{PINNED_ROOT}/deploy_backend_blue_green_safety.sh",
    f"{PINNED_ROOT}/require_deploy_capacity.sh",
)


def _generation(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def verify_marker(
    path: str,
    transaction_id: str,
    *,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> None:
    if TRANSACTION_RE.fullmatch(transaction_id) is None:
        raise RuntimeError("PITR maintenance transaction id is invalid")

    before = os.lstat(path)
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_uid != expected_uid
        or before.st_gid != expected_gid
        or before.st_nlink != 1
        or before.st_size != 33
    ):
        raise RuntimeError("PITR maintenance marker metadata is unsafe")

    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if _generation(opened) != _generation(before):
            raise RuntimeError("PITR maintenance marker changed before open")
        content = os.read(descriptor, 34)
        after = os.fstat(descriptor)
        if _generation(after) != _generation(opened):
            raise RuntimeError("PITR maintenance marker changed while being read")
    finally:
        os.close(descriptor)

    final = os.lstat(path)
    if _generation(final) != _generation(after):
        raise RuntimeError("PITR maintenance marker path changed while being read")
    if content != f"{transaction_id}\n".encode("ascii"):
        raise RuntimeError("PITR maintenance marker belongs to another transaction")


def _verify_runtime_file(path: str) -> None:
    parent = os.lstat(os.path.dirname(path))
    if (
        not stat.S_ISDIR(parent.st_mode)
        or stat.S_ISLNK(parent.st_mode)
        or parent.st_uid != 0
        or parent.st_gid != 0
        or parent.st_mode & 0o022
    ):
        raise RuntimeError(f"PITR scrub runtime helper parent is unsafe: {path}")
    metadata = os.lstat(path)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o022
        or metadata.st_mode & 0o111 == 0
    ):
        raise RuntimeError(f"PITR scrub runtime helper is unsafe: {path}")


def verify_pinned_runtime(paths: tuple[str, ...]) -> None:
    if paths != PINNED_RUNTIME_PATHS:
        raise RuntimeError("PITR scrub runtime helper paths are not pinned")
    for path in paths:
        _verify_runtime_file(path)


def main() -> int:
    if os.path.abspath(__file__) != PINNED_VALIDATOR:
        raise RuntimeError("PITR maintenance marker validator path is not pinned")
    _verify_runtime_file(PINNED_VALIDATOR)
    if len(sys.argv) == 3 and sys.argv[1] == "marker":
        verify_marker(MARKER_PATH, sys.argv[2])
        return 0
    if len(sys.argv) == 6 and sys.argv[1] == "runtime":
        verify_pinned_runtime(tuple(sys.argv[2:]))
        return 0
    if len(sys.argv) == 7 and sys.argv[1] == "pre-source":
        verify_pinned_runtime(tuple(sys.argv[3:]))
        verify_marker(MARKER_PATH, sys.argv[2])
        return 0
    raise RuntimeError(
        "usage: verify_pitr_maintenance_marker.py marker TRANSACTION_ID | "
        "runtime RUNTIME LOCK SAFETY CAPACITY | "
        "pre-source TRANSACTION_ID RUNTIME LOCK SAFETY CAPACITY"
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"PITR maintenance marker attestation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
