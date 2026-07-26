import json
import subprocess
from io import BytesIO
from types import SimpleNamespace

import pytest

from scripts.ha import patroni_compose_runtime


def _config(tmp_path, *, ready_attempts=2):
    return SimpleNamespace(
        project_dir=tmp_path,
        compose_file="compose.yml",
        ready_url="http://127.0.0.1:18080/api/ready",
        ready_attempts=ready_attempts,
    )


def _runtime(
    tmp_path,
    runner,
    writer=lambda *_args, **_kwargs: None,
    *,
    docker_runner=None,
):
    kwargs = {
        "compose_runner": runner,
        "atomic_writer": writer,
    }
    if docker_runner is not None:
        kwargs["docker_runner"] = docker_runner
    return patroni_compose_runtime.ComposeRuntime(_config(tmp_path), **kwargs)


def test_run_compose_preserves_reviewed_command_and_working_directory(
    tmp_path, monkeypatch
):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(patroni_compose_runtime.subprocess, "run", run)

    result = patroni_compose_runtime.run_compose(
        _config(tmp_path),
        "ps",
        "--quiet",
        check=False,
        timeout=17,
    )

    assert result.returncode == 0
    assert calls == [
        (
            [
                "docker",
                "compose",
                "--profile",
                "bluegreen",
                "-f",
                "compose.yml",
                "ps",
                "--quiet",
            ],
            {
                "cwd": tmp_path,
                "check": False,
                "text": True,
                "capture_output": True,
                "timeout": 17,
            },
        )
    ]


def test_running_services_filters_oneoff_records_and_accepts_json_lines(tmp_path):
    records = [
        {
            "Service": "app-blue",
            "Labels": "com.docker.compose.oneoff=False,other=value",
        },
        {
            "Service": "restore-drill",
            "Labels": {"com.docker.compose.oneoff": "True"},
        },
    ]

    def runner(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="\n".join(json.dumps(record) for record in records),
            stderr="",
        )

    assert _runtime(tmp_path, runner).running_services() == {"app-blue"}


def test_running_services_fails_closed_without_oneoff_identity(tmp_path):
    def runner(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"Service": "app", "Labels": "other=value"}),
            stderr="",
        )

    with pytest.raises(RuntimeError, match="one-off identity"):
        _runtime(tmp_path, runner).running_services()


def test_labeled_service_fence_uses_exact_project_and_service_filters(tmp_path):
    calls = []
    container_exists = True
    container_id = "a" * 12

    def docker(*args, **_kwargs):
        nonlocal container_exists
        calls.append(args)
        if args[:2] == ("ps", "--all"):
            return SimpleNamespace(
                returncode=0,
                stdout=f"{container_id}\n" if container_exists else "",
                stderr="",
            )
        if args[0] == "rm":
            container_exists = False
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    runtime = _runtime(
        tmp_path,
        lambda *_args, **_kwargs: None,
        docker_runner=docker,
    )

    assert runtime.fence_labeled_service_containers("communications-worker")
    assert calls[0] == (
        "ps",
        "--all",
        "--quiet",
        "--filter",
        f"label=com.docker.compose.project={tmp_path.name}",
        "--filter",
        "label=com.docker.compose.service=communications-worker",
    )
    assert ("stop", "--timeout", "10", container_id) in calls
    assert ("rm", "--force", container_id) in calls
    assert calls[-1][:2] == ("ps", "--all")
    assert container_exists is False


def test_genuinely_absent_worker_in_old_compose_is_safe(tmp_path):
    docker_calls = []

    def docker(*args, **_kwargs):
        docker_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    runtime = _runtime(
        tmp_path,
        lambda *_args, **_kwargs: None,
        docker_runner=docker,
    )

    state = runtime.worker_runtime_state(
        service="communications-worker",
        role="standby",
        running_services=set(),
        definition_probe=lambda *_args, **_kwargs: False,
        role_probe=lambda *_args, **_kwargs: pytest.fail("role probe must not run"),
    )

    assert state == patroni_compose_runtime.WorkerRuntimeState(
        defined=False,
        running=False,
        role_matches=False,
        unsafe_mismatch=False,
    )
    assert docker_calls == []


@pytest.mark.parametrize(
    ("recreate", "expected"),
    [
        (False, ("up", "-d", "--no-deps", "app")),
        (True, ("up", "-d", "--no-deps", "--force-recreate", "app")),
    ],
)
def test_start_service_preserves_recreate_contract(
    tmp_path, recreate, expected
):
    calls = []

    def runner(_config, *args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    _runtime(tmp_path, runner).start_service("app", recreate=recreate)

    assert calls == [expected]


def test_stop_service_escalates_and_verifies_exact_service(tmp_path):
    calls = []
    inventories = iter(["container-id\n", ""])

    def runner(_config, *args, **_kwargs):
        calls.append(args)
        if args[:3] == ("ps", "--all", "--quiet"):
            return SimpleNamespace(
                returncode=0,
                stdout=next(inventories),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="still running")

    _runtime(tmp_path, runner).stop_service_verified("communications-worker")

    assert calls == [
        ("rm", "--stop", "--force", "communications-worker"),
        ("ps", "--all", "--quiet", "communications-worker"),
        ("kill", "--signal", "SIGKILL", "communications-worker"),
        ("rm", "--force", "communications-worker"),
        ("ps", "--all", "--quiet", "communications-worker"),
    ]


def test_stop_service_fails_when_container_survives_force_removal(tmp_path):
    def runner(_config, *args, **_kwargs):
        if args[:3] == ("ps", "--all", "--quiet"):
            return SimpleNamespace(
                returncode=0,
                stdout="container-id\n",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="still running")

    with pytest.raises(RuntimeError, match="could not fence.*communications-worker"):
        _runtime(tmp_path, runner).stop_service_verified("communications-worker")


def test_proxy_reconciliation_is_atomic_and_restart_is_runtime_gated(tmp_path):
    writes = []
    calls = []

    def writer(path, content, **kwargs):
        writes.append((path, content, kwargs))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def runner(_config, *args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    runtime = _runtime(tmp_path, runner, writer)
    running = {"app-green", "api-proxy"}

    assert runtime.reconcile_container_proxy_upstream(
        "app-green",
        running_services=running,
    )
    assert writes == [
        (
            tmp_path / "api-proxy" / "upstream.conf",
            "proxy_pass http://app-green:8000;\n",
            {"mode": 0o644},
        )
    ]
    assert runtime.refresh_container_proxy_dns(running_services=running)
    assert calls == [("restart", "api-proxy")]
    assert not runtime.refresh_container_proxy_dns(running_services={"app-green"})


class _ReadyResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return BytesIO(
            json.dumps(
                {
                    "api": "ready",
                    "database_writable": True,
                    "scheduler_runtime": {
                        "expected": True,
                        "status": "running",
                    },
                }
            ).encode()
        ).read()


def test_scheduler_probe_accepts_only_ready_owned_runtime(tmp_path, monkeypatch):
    calls = []

    def urlopen(url, *, timeout):
        calls.append((url, timeout))
        return _ReadyResponse()

    monkeypatch.setattr(patroni_compose_runtime.urllib.request, "urlopen", urlopen)

    patroni_compose_runtime.wait_scheduler_running(_config(tmp_path))

    assert calls == [("http://127.0.0.1:18080/api/ready", 5)]


def test_scheduler_probe_exhaustion_keeps_original_error_contract(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        patroni_compose_runtime.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
    )
    monkeypatch.setattr(patroni_compose_runtime.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="did not acquire runtime ownership"):
        patroni_compose_runtime.wait_scheduler_running(
            _config(tmp_path, ready_attempts=2)
        )
