from __future__ import annotations

import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest
import yaml

from scripts.ha.pitr_pinned_ssh import PATRONI_NODES
from scripts.ops import cache_api_image as controller
from scripts.ops import cache_api_image_remote as remote

IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "a" * 64


@pytest.mark.parametrize("value", ["ghcr.io/mvnby/air-api/backend:main", IMAGE + "; id", "docker.io/other@sha256:" + "a" * 64])
def test_mutable_or_foreign_image_rejected_before_ssh(value):
    with pytest.raises(ValueError):
        controller.remote_command(PATRONI_NODES[0], value)


def test_controller_runs_with_only_python_standard_library():
    result = subprocess.run(
        [sys.executable, "-I", "-S", controller.__file__, "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("node", PATRONI_NODES)
def test_remote_command_is_fixed_and_compiles(node):
    command = shlex.split(controller.remote_command(node, IMAGE))
    assert command[:2] == ["python3", "-c"]
    compile(command[2], "<remote-cache>", "exec")
    assert node.project_dir + "/.deploy.lock" in command[2]
    assert "exec-wait" in command[2]
    assert "safe_deploy_lock.py" in command[2]
    assert "docker compose" not in command[2]


def prepared_remote(monkeypatch, tmp_path, *, pull_fails=False, wrong_digest=False):
    calls = []
    directories = []
    real_temporary_directory = tempfile.TemporaryDirectory

    def private_directory(**kwargs):
        context = real_temporary_directory(prefix=kwargs["prefix"], dir=tmp_path)
        directories.append(context.name)
        return context

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[0] != "docker":
            assert "verify" in argv and kwargs["pass_fds"] == (9,)
        elif argv[1] == "login":
            assert argv[-1] == "--password-stdin"
            assert kwargs["input"] == "test-private-registry-token"
            assert Path(kwargs["env"]["DOCKER_CONFIG"]).is_dir()
        elif argv[1] == "pull" and pull_fails:
            return subprocess.CompletedProcess(argv, 1, "", "sensitive remote error")
        elif argv[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps([{
                "RepoDigests": [] if wrong_digest else [IMAGE], "Os": "linux",
            }]), "")
        else:
            assert argv[1:] == ["pull", IMAGE]
        return subprocess.CompletedProcess(argv, 0, "", "")

    def endpoint(path):
        if path == "8008/patroni":
            return {"state": "running", "role": "primary", "patroni": {"name": "mvn-api"}}
        assert path == "18080/api/ready"
        return {"status": "ok"}

    monkeypatch.setenv("API_DEPLOY_LOCK_FD", "9")
    monkeypatch.setattr(remote.subprocess, "run", run)
    monkeypatch.setattr(remote.tempfile, "TemporaryDirectory", private_directory)
    monkeypatch.setattr(remote, "endpoint", endpoint)
    monkeypatch.setattr(remote, "active_api", lambda _: ("blue", "existing-container", "existing-image"))
    monkeypatch.setattr(remote.sys, "stdin", io.StringIO(json.dumps({
        "username": "mvnby", "token": "test-private-registry-token",
    })))
    return calls, directories


def test_caches_exact_image_without_activation_or_persisted_credentials(monkeypatch, tmp_path, capsys):
    calls, directories = prepared_remote(monkeypatch, tmp_path)
    remote.cache_image("/opt/air-api", IMAGE)
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["image"] == IMAGE
    assert receipt["api_unchanged"] is True
    assert receipt["ephemeral_registry_config_removed"] is True
    assert directories and all(not Path(path).exists() for path in directories)
    assert [call[0][1] for call in calls if call[0][0] == "docker"] == ["login", "pull", "image"]
    assert "test-private-registry-token" not in json.dumps(receipt)


@pytest.mark.parametrize("failure", ["pull", "digest"])
def test_registry_configuration_removed_when_pull_or_digest_check_fails(monkeypatch, tmp_path, capsys, failure):
    _, directories = prepared_remote(monkeypatch, tmp_path, pull_fails=failure == "pull", wrong_digest=failure == "digest")
    with pytest.raises(RuntimeError, match="cache step failed|digest does not match"):
        remote.cache_image("/opt/air-api", IMAGE)
    assert directories and all(not Path(path).exists() for path in directories)
    assert "test-private-registry-token" not in capsys.readouterr().out


@pytest.mark.parametrize("blocker", ["lock", "role"])
def test_no_registry_login_without_primary_and_lock(monkeypatch, tmp_path, blocker):
    calls, directories = prepared_remote(monkeypatch, tmp_path)
    if blocker == "lock":
        monkeypatch.delenv("API_DEPLOY_LOCK_FD")
    else:
        monkeypatch.setattr(remote, "endpoint", lambda _: {"state": "running", "role": "replica"})
    with pytest.raises(RuntimeError, match="lock is absent|not primary"):
        remote.cache_image("/opt/air-api", IMAGE)
    assert not directories
    assert not any(call[0][0] == "docker" for call in calls)


def test_workflow_keeps_main_ci_gate_and_minimal_registry_permission():
    workflow = yaml.load((controller.REPO_ROOT / ".github/workflows/cache-api-image.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["concurrency"]["group"] == "production-release"
    job = workflow["jobs"]["cache"]
    assert job["environment"] == "production-api"
    assert job["permissions"]["packages"] == "read"
    steps = job["steps"]
    ci_gate = next(step for step in steps if step.get("name") == "Verify Exact Main CI")
    assert "release_scope.py --manual" in ci_gate["run"]
    assert '--sha "${GITHUB_SHA}"' in ci_gate["run"]
    assert "--github-output" in ci_gate["run"] and "--summary" in ci_gate["run"]
    cleanup = steps[-1]
    assert cleanup["if"] == "always()"
    assert "cache-api-image-key" in cleanup["run"]


def test_controller_passes_token_only_to_verified_primary_stdin(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GITHUB_ACTOR", "mvnby")
    monkeypatch.setattr(sys, "argv", ["cache", "--image", IMAGE, "--identity-file", str(tmp_path / "key")])
    monkeypatch.setattr(sys, "stdin", io.StringIO("test-private-registry-token"))
    monkeypatch.setattr(controller, "create_context", lambda *_: object())
    checked = []
    monkeypatch.setattr(controller, "validate_effective_config", lambda node, context: checked.append(node))

    def discover(*, context, runner):
        assert checked == list(PATRONI_NODES)
        return SimpleNamespace(primary=PATRONI_NODES[0])

    def run(argv, stdin=None):
        assert "test-private-registry-token" not in " ".join(argv)
        assert json.loads(stdin) == {"username": "mvnby", "token": "test-private-registry-token"}
        return subprocess.CompletedProcess(argv, 0, json.dumps({
            "image": IMAGE, "primary": "mvn-api", "digest_verified": True,
            "deployment_lock_verified": True, "api_unchanged": True,
            "ephemeral_registry_config_removed": True,
        }), "")

    monkeypatch.setattr(controller, "discover_cluster_topology", discover)
    monkeypatch.setattr(controller, "ssh_args", lambda node, context: ["ssh", node.alias])
    monkeypatch.setattr(controller, "run", run)
    assert controller.main() == 0
    assert "test-private-registry-token" not in capsys.readouterr().out
