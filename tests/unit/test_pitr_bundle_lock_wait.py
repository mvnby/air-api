import base64
import errno
import fcntl
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import pytest

from scripts.ha.pitr_bundle_transport import REMOTE_RELEASE_BUNDLE_EXECUTOR


def _namespace(tmp_path: Path) -> tuple[dict, Path, Path, Path]:
    source = REMOTE_RELEASE_BUNDLE_EXECUTOR.rsplit(
        "\nraise SystemExit(main())", 1
    )[0]
    remote = {"__name__": "pitr_bundle_lock_wait_test"}
    exec(compile(source, "<pitr-bundle-lock-wait>", "exec"), remote)
    project = tmp_path / "project"
    project.mkdir(mode=0o700)
    compose = project / "docker-compose.patroni.yml"
    tool = tmp_path / "tool"
    remote.update(
        {
            "ROOT_UID": os.geteuid(),
            "ROOT_GID": os.getegid(),
            "LOCK_PATH": str(tmp_path / "pitr.lock"),
            "BASE_MODES": {str(tool): 0o755},
            "PROJECT_COMPOSE": {str(project): str(compose)},
            "validate_parent": lambda _path: None,
        }
    )
    return remote, project, compose, tool


def _payload(remote: dict, project: Path, compose: Path, tool: Path) -> bytes:
    contents = {str(compose): b"compose", str(tool): b"tool"}
    modes = {str(compose): 0o644, str(tool): 0o755}
    files = [
        {
            "content": base64.b64encode(contents[path]).decode("ascii"),
            "mode": modes[path],
            "path": path,
            "sha256": hashlib.sha256(contents[path]).hexdigest(),
        }
        for path in sorted(contents)
    ]
    body = {"files": files, "project_dir": str(project), "version": 1}
    return remote["canonical"](
        {**body, "release_sha256": hashlib.sha256(remote["canonical"](body)).hexdigest()}
    )


def test_open_lock_retries_transient_contention(monkeypatch, tmp_path):
    remote, *_ = _namespace(tmp_path)
    attempts = 0
    sleeps = []

    def flock(_descriptor, _operation):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise BlockingIOError

    monkeypatch.setattr(remote["fcntl"], "flock", flock)
    monkeypatch.setattr(remote["time"], "monotonic", lambda: 10.0)
    monkeypatch.setattr(remote["time"], "sleep", sleeps.append)

    descriptor = remote["open_lock"](remote["LOCK_PATH"], deadline=40.0)
    try:
        assert attempts == 3
        assert sleeps == [0.25, 0.25]
    finally:
        os.close(descriptor)


def test_open_lock_waits_for_real_flock_release(tmp_path):
    remote, *_ = _namespace(tmp_path)
    remote["LOCK_RETRY_SECONDS"] = 0.01
    holder = os.open(remote["LOCK_PATH"], os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    released = threading.Event()

    def release():
        time.sleep(0.03)
        fcntl.flock(holder, fcntl.LOCK_UN)
        os.close(holder)
        released.set()

    thread = threading.Thread(target=release)
    thread.start()
    started = time.monotonic()
    descriptor = remote["open_lock"](
        remote["LOCK_PATH"], deadline=started + 0.5
    )
    try:
        assert released.wait(0.2)
        assert time.monotonic() - started >= 0.02
    finally:
        os.close(descriptor)
        thread.join()


def test_open_lock_timeout_closes_descriptor(monkeypatch, tmp_path):
    remote, *_ = _namespace(tmp_path)
    descriptors = []

    def busy(descriptor, _operation):
        descriptors.append(descriptor)
        raise BlockingIOError

    monkeypatch.setattr(remote["fcntl"], "flock", busy)
    monkeypatch.setattr(remote["time"], "monotonic", lambda: 30.0)

    with pytest.raises(RuntimeError, match="another PITR or deploy operation is active"):
        remote["open_lock"](remote["LOCK_PATH"], deadline=30.0)
    with pytest.raises(OSError) as error:
        os.fstat(descriptors[0])
    assert error.value.errno == errno.EBADF


def test_open_lock_does_not_retry_other_errors(monkeypatch, tmp_path):
    remote, *_ = _namespace(tmp_path)
    descriptors = []

    def denied(descriptor, _operation):
        descriptors.append(descriptor)
        raise PermissionError("denied")

    monkeypatch.setattr(remote["fcntl"], "flock", denied)
    monkeypatch.setattr(
        remote["time"], "sleep", lambda _seconds: pytest.fail("unexpected retry")
    )

    with pytest.raises(PermissionError, match="denied"):
        remote["open_lock"](remote["LOCK_PATH"], deadline=30.0)
    with pytest.raises(OSError) as error:
        os.fstat(descriptors[0])
    assert error.value.errno == errno.EBADF


def test_open_lock_metadata_failure_is_immediate(monkeypatch, tmp_path):
    remote, *_ = _namespace(tmp_path)
    lock_path = Path(remote["LOCK_PATH"])
    lock_path.touch(mode=0o600)
    lock_path.chmod(0o620)
    monkeypatch.setattr(
        remote["time"], "sleep", lambda _seconds: pytest.fail("metadata failure waited")
    )
    monkeypatch.setattr(
        remote["fcntl"], "flock", lambda *_args: pytest.fail("unsafe lock was acquired")
    )

    with pytest.raises(RuntimeError, match="release lock metadata is unsafe"):
        remote["open_lock"](str(lock_path), deadline=30.0)


def test_execute_shares_one_deadline_across_both_locks(monkeypatch, tmp_path):
    remote, project, compose, tool = _namespace(tmp_path)
    deadlines = []
    descriptors = []

    def open_lock(path, *, deadline):
        deadlines.append((path, deadline))
        if len(deadlines) == 1:
            descriptor = os.open(os.devnull, os.O_RDONLY)
            descriptors.append(descriptor)
            return descriptor
        raise RuntimeError("stop after lock proof")

    monkeypatch.setattr(remote["time"], "monotonic", lambda: 12.5)
    remote["open_lock"] = open_lock

    with pytest.raises(RuntimeError, match="stop after lock proof"):
        remote["execute"](
            "inspect",
            "0123456789abcdef0123456789abcdef",
            str(project),
            compose.name,
            _payload(remote, project, compose, tool),
        )
    assert deadlines == [
        (remote["LOCK_PATH"], 42.5),
        (str(project / ".deploy.lock"), 42.5),
    ]
    with pytest.raises(OSError) as error:
        os.fstat(descriptors[0])
    assert error.value.errno == errno.EBADF
