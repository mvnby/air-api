"""Self-contained fail-closed proof used only for primary PITR provisioning."""

from __future__ import annotations


FENCED_PROVISION_HELPERS = r'''
FENCED_ROLE_AGENT_UNIT = "mvn-patroni-role-agent.service"
FENCED_RUNTIME_SERVICES = ("app", "app-blue", "app-green", "bot")
FENCED_CLEAN_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "DOCKER_CONTEXT": "default",
}


def _read_fenced_runtime_state(project_dir):
    path = os.path.join(project_dir, ".ha-runtime-role")
    before = os.lstat(path)
    expected = b"fencing\n"
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size != len(expected)
    ):
        raise RuntimeError("primary fenced runtime state metadata is unsafe")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError("primary fenced runtime state changed while opening")
        payload = os.read(descriptor, len(expected) + 1)
        if payload != expected or os.read(descriptor, 1):
            raise RuntimeError("primary runtime is not in the exact fencing state")
        finished = os.fstat(descriptor)
        generation = (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        if generation != (
            finished.st_dev,
            finished.st_ino,
            finished.st_size,
            finished.st_mtime_ns,
            finished.st_ctime_ns,
        ):
            raise RuntimeError("primary fenced runtime state changed while reading")
        return generation
    finally:
        os.close(descriptor)


def _require_fenced_role_agent_inactive():
    result = subprocess.run(
        ["/usr/bin/systemctl", "is-active", FENCED_ROLE_AGENT_UNIT],
        env=FENCED_CLEAN_ENV,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 3 or result.stdout.strip() != "inactive":
        raise RuntimeError("primary role agent is not exactly inactive")


def _require_fenced_runtime_empty(project_dir, compose_file):
    compose_path = os.path.join(project_dir, compose_file)
    result = subprocess.run(
        [
            "/usr/bin/docker",
            "compose",
            "--profile",
            "bluegreen",
            "--project-directory",
            project_dir,
            "-f",
            compose_path,
            "ps",
            "--all",
            "-q",
            *FENCED_RUNTIME_SERVICES,
        ],
        env=FENCED_CLEAN_ENV,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError("primary fenced runtime inventory failed")
    if result.stdout.strip():
        raise RuntimeError("primary fenced runtime still has API or bot containers")


def prove_fenced_provision_state(project_dir, compose_file):
    first = _read_fenced_runtime_state(project_dir)
    _require_fenced_role_agent_inactive()
    _require_fenced_runtime_empty(project_dir, compose_file)
    second = _read_fenced_runtime_state(project_dir)
    _require_fenced_role_agent_inactive()
    if second != first:
        raise RuntimeError("primary fenced runtime state generation changed")
'''.strip()
