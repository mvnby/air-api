#!/usr/bin/env python3
"""Open or verify the inherited deployment lock without following symlinks."""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import stat
import sys
from pathlib import Path


LOCK_FD = 9


def _verify_self() -> None:
    expected = os.environ.get("API_DEPLOY_LOCK_HELPER_SHA256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RuntimeError("safe deployment lock helper digest is missing")
    path = Path(__file__).resolve()
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o022
        or hashlib.sha256(path.read_bytes()).hexdigest() != expected
    ):
        raise RuntimeError("safe deployment lock helper source is unreviewed")


def _validate_parent(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    metadata = os.lstat(parent)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise RuntimeError("deployment lock parent directory is unsafe")


def _validate_open_file(path: str, descriptor: int, *, allow_legacy_mode: bool = False) -> None:
    before = os.lstat(path)
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_nlink != 1
        or (stat.S_IMODE(before.st_mode) != 0o600 and not (
            allow_legacy_mode and stat.S_IMODE(before.st_mode) == 0o644
        ))
        or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        or opened.st_nlink != 1
    ):
        raise RuntimeError("deployment lock file is unsafe")


def _open(path: str) -> int:
    _validate_parent(path)
    flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    created = False
    try:
        descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
    except FileExistsError:
        descriptor = os.open(path, flags)
    if created:
        os.fchmod(descriptor, 0o600)
    _validate_open_file(path, descriptor, allow_legacy_mode=not created)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if not created and stat.S_IMODE(os.fstat(descriptor).st_mode) == 0o644:
        os.fchmod(descriptor, 0o600)
    _validate_open_file(path, descriptor)
    return descriptor


def _verify(path: str, descriptor: int) -> None:
    _validate_parent(path)
    _validate_open_file(path, descriptor)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def main() -> int:
    _verify_self()
    if len(sys.argv) < 4 or sys.argv[1] not in {"exec", "verify"}:
        raise RuntimeError("usage: safe_deploy_lock.py exec|verify LOCK command...")
    operation, path = sys.argv[1:3]
    if operation == "verify":
        if len(sys.argv) != 4 or not sys.argv[3].isdigit():
            raise RuntimeError("verify requires one numeric inherited descriptor")
        _verify(path, int(sys.argv[3]))
        return 0
    descriptor = _open(path)
    if descriptor != LOCK_FD:
        os.dup2(descriptor, LOCK_FD, inheritable=True)
        os.close(descriptor)
    else:
        os.set_inheritable(descriptor, True)
    environment = os.environ.copy()
    environment["API_DEPLOY_LOCK_FD"] = str(LOCK_FD)
    os.execvpe(sys.argv[3], sys.argv[3:], environment)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"safe_deploy_lock status=failed error={exc}", file=sys.stderr)
        raise SystemExit(1)
