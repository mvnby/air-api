#!/usr/bin/env python3
"""Run the PITR host-asset installer under the shared hardened host lock."""

from __future__ import annotations

import fcntl
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence


LOCK_PATH = Path("/run/lock/mvn-postgres-pitr-prerequisites.lock")
ALLOWED_PROJECT_DIRS = {"/opt/air-api", "/opt/mvn-reserve"}
ALLOWED_ENV_NAMES = (
    "PROJECT_DIR",
    "COMPOSE_FILE",
    "ENABLE_TIMERS",
)


def _validate_installer(path: Path, *, expected_uid: int) -> None:
    if not path.is_absolute():
        raise RuntimeError("installer path must be absolute")
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != expected_uid
        or metadata.st_mode & 0o022
    ):
        raise RuntimeError("installer must be an owner-controlled regular non-symlink")


def _open_lock(
    path: Path,
    *,
    expected_uid: int,
    busy_message: str = "another PITR host operation is active",
) -> int:
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("required lock protection is unavailable")
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != expected_uid
        or metadata.st_nlink != 1
    ):
        os.close(descriptor)
        raise RuntimeError("PITR host lock metadata is unsafe")
    os.fchmod(descriptor, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise RuntimeError(busy_message) from exc
    return descriptor


def run_locked_install(
    installer: Path,
    arguments: Sequence[str],
    *,
    environ: Mapping[str, str],
    expected_uid: int,
    lock_path: Path = LOCK_PATH,
    deploy_lock_path: Path | None = None,
) -> int:
    _validate_installer(installer, expected_uid=expected_uid)
    lock_fd = _open_lock(lock_path, expected_uid=expected_uid)
    if deploy_lock_path is None:
        project_dir = environ.get("PROJECT_DIR", "")
        if project_dir not in ALLOWED_PROJECT_DIRS:
            os.close(lock_fd)
            raise RuntimeError("unreviewed project directory for deploy lock")
        deploy_lock_path = Path(project_dir) / ".deploy.lock"
    try:
        deploy_lock_fd = _open_lock(
            deploy_lock_path,
            expected_uid=expected_uid,
            busy_message="a project deployment is active",
        )
    except BaseException:
        os.close(lock_fd)
        raise
    environment = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/root",
        "LANG": "C",
        "LC_ALL": "C",
        "DOCKER_CONTEXT": "default",
        "PITR_INSTALL_LOCK_FD": str(lock_fd),
        "PITR_INSTALL_DEPLOY_LOCK_FD": str(deploy_lock_fd),
    }
    for name in ALLOWED_ENV_NAMES:
        if name in environ:
            environment[name] = environ[name]
    try:
        result = subprocess.run(
            [str(installer), *arguments],
            env=environment,
            pass_fds=(lock_fd, deploy_lock_fd),
            check=False,
        )
        return result.returncode
    finally:
        os.close(deploy_lock_fd)
        os.close(lock_fd)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if not arguments:
        print("locked PITR install: installer path is required", file=sys.stderr)
        return 64
    if os.geteuid() != 0:
        print("locked PITR install: root execution is required", file=sys.stderr)
        return 77
    try:
        return run_locked_install(
            Path(arguments[0]),
            arguments[1:],
            environ=os.environ,
            expected_uid=0,
        )
    except (OSError, RuntimeError) as exc:
        print(f"locked PITR install: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
