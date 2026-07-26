#!/usr/bin/env python3
"""Run the installed Patroni role agent once with its attested node environment."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from pathlib import Path


ROLE_ENV_PATH = Path("/etc/default/mvn-patroni-role-agent")
ROLE_AGENT_PATH = Path("/usr/local/sbin/mvn-patroni-role-agent")
PYTHON_PATH = Path("/usr/bin/python3")
MAX_ENVIRONMENT_BYTES = 16_384
MAX_AGENT_BYTES = 1_048_576
PRODUCTION_NODE_NAMES = {
    "/opt/air-api": "mvn-api",
    "/opt/mvn-reserve": "zakup",
}
BASE_EXEC_ENVIRONMENT = {
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "PYTHONNOUSERSITE": "1",
}


def expected_role_environment(project_dir: str) -> dict[str, str]:
    patroni_name = PRODUCTION_NODE_NAMES.get(project_dir)
    if patroni_name is None:
        raise ValueError("unreviewed role-agent project directory")
    return {
        "HA_PROJECT_DIR": project_dir,
        "HA_COMPOSE_FILE": "docker-compose.patroni.yml",
        "HA_PATRONI_URL": "http://127.0.0.1:8008/patroni",
        "HA_PATRONI_SCOPE": "mvn-postgres",
        "HA_PATRONI_NAME": patroni_name,
        "HA_PATRONI_MAX_DCS_AGE_SECONDS": "20",
        "HA_READY_URL": "http://127.0.0.1:18080/api/ready",
        "HA_APP_SERVICE": "",
        "HA_PRIMARY_SYSTEMD_UNITS": (
            "mvn-postgres-wal-upload.timer mvn-postgres-basebackup.timer"
        ),
        "HA_ROLE_POLL_SECONDS": "3",
        "HA_PROMOTION_DELAY_SECONDS": "8",
        "HA_READY_ATTEMPTS": "30",
    }


def _read_root_regular(
    path: Path,
    *,
    mode: int,
    maximum: int,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or metadata.st_gid != expected_gid
            or stat.S_IMODE(metadata.st_mode) != mode
            or metadata.st_nlink != 1
            or metadata.st_size > maximum
        ):
            raise ValueError(f"unsafe role-agent asset: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(maximum + 1)
        if len(content) > maximum:
            raise ValueError(f"oversized role-agent asset: {path}")
        return content
    finally:
        os.close(descriptor)


def attest_role_environment(
    project_dir: str,
    *,
    path: Path = ROLE_ENV_PATH,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> dict[str, str]:
    content = _read_root_regular(
        path,
        mode=0o600,
        maximum=MAX_ENVIRONMENT_BYTES,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("role-agent environment is not UTF-8") from exc
    actual: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("role-agent environment contains an invalid line")
        name, value = line.split("=", 1)
        if not name or name in actual:
            raise ValueError("role-agent environment contains an invalid key set")
        actual[name] = value
    if actual != expected_role_environment(project_dir):
        raise ValueError("role-agent environment differs from the reviewed node contract")
    return actual


def run_once(
    project_dir: str,
    expected_agent_sha256: str,
    *,
    environment_path: Path = ROLE_ENV_PATH,
    agent_path: Path = ROLE_AGENT_PATH,
    python_path: Path = PYTHON_PATH,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> None:
    if len(expected_agent_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_agent_sha256
    ):
        raise ValueError("invalid expected role-agent digest")
    role_environment = attest_role_environment(
        project_dir,
        path=environment_path,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    agent_content = _read_root_regular(
        agent_path,
        mode=0o755,
        maximum=MAX_AGENT_BYTES,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if hashlib.sha256(agent_content).hexdigest() != expected_agent_sha256:
        raise ValueError("installed role-agent digest differs from the reviewed source")
    clean_environment = {**BASE_EXEC_ENVIRONMENT, **role_environment}
    os.execve(
        python_path,
        [str(python_path), str(agent_path), "--once"],
        clean_environment,
    )


def main() -> None:
    if len(sys.argv) != 3:
        raise ValueError(
            "usage: patroni_role_agent_once_env.py "
            "/opt/air-api|/opt/mvn-reserve EXPECTED_AGENT_SHA256"
        )
    run_once(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f"role-agent one-shot environment attestation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
