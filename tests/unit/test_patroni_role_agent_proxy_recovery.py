import fcntl
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import patroni_role_agent
from scripts.ha.patroni_role_agent import AgentConfig, reconcile


@pytest.fixture(autouse=True)
def _safe_host_contracts(monkeypatch):
    monkeypatch.setattr(
        patroni_role_agent, "read_maintenance_transaction_id", lambda: None
    )
    monkeypatch.setattr(
        patroni_role_agent,
        "_require_fresh_primary_or_fence",
        lambda _config, _boundary: None,
    )
    monkeypatch.setattr(
        patroni_role_agent, "_cancel_pitr_operations", lambda _config: []
    )


def _config(tmp_path: Path) -> AgentConfig:
    (tmp_path / ".active-api-slot").write_text("blue\n", encoding="utf-8")
    return AgentConfig(
        project_dir=tmp_path,
        compose_file="compose.yml",
        patroni_url="http://127.0.0.1:8008/patroni",
        patroni_scope="mvn-postgres",
        patroni_name="mvn-api",
        max_dcs_age_seconds=20,
        ready_url="http://127.0.0.1:18080/api/ready",
        app_role_env=tmp_path / ".ha-app-role.env",
        bot_role_env=tmp_path / ".ha-bot-role.env",
        state_file=tmp_path / ".ha-runtime-role",
        deploy_lock=tmp_path / ".deploy.lock",
        active_slot_file=tmp_path / ".active-api-slot",
        app_service="",
        primary_systemd_units=(),
        poll_seconds=3,
        promotion_delay_seconds=0,
        ready_attempts=2,
    )


class _Runtime:
    def __init__(self, *services: str, fail_proxy_restart: bool = False):
        self.services = set(services or ("api-proxy",))
        self.fail_proxy_restart = fail_proxy_restart
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, _config, *args, **_kwargs):
        self.calls.append(args)
        if args[:3] == ("ps", "--status", "running"):
            return SimpleNamespace(
                returncode=0,
                stdout="\n".join(sorted(self.services)) + "\n",
                stderr="",
            )
        if args[:3] == ("ps", "--all", "--quiet"):
            service = args[-1]
            output = f"id-{service}\n" if service in self.services else ""
            return SimpleNamespace(returncode=0, stdout=output, stderr="")
        if args == ("restart", "api-proxy") and self.fail_proxy_restart:
            raise subprocess.CalledProcessError(1, args)
        if args[0] == "up":
            self.services.add(args[-1])
        elif args[0] in {"rm", "kill", "stop"}:
            self.services.discard(args[-1])
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_primary_refreshes_container_proxy_dns_before_stable_readiness(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    runtime = _Runtime()
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)

    def ready(_config):
        assert ("restart", "api-proxy") in runtime.calls

    monkeypatch.setattr(patroni_role_agent, "_wait_ready", ready)

    assert reconcile(config, "primary") is True
    assert ("restart", "api-proxy") in runtime.calls
    assert not any(call[0] == "up" and call[-1] == "bot" for call in runtime.calls)
    assert config.state_file.read_text(encoding="utf-8") == "primary\n"


def test_readiness_failure_releases_deploy_lock_for_exact_retry(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    config.state_file.write_text("fencing\n", encoding="utf-8")
    runtime = _Runtime()
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(
        patroni_role_agent,
        "_wait_ready",
        lambda _config: (_ for _ in ()).throw(RuntimeError("not ready")),
    )

    with pytest.raises(RuntimeError, match="not ready"):
        reconcile(config, "primary")

    with config.deploy_lock.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    assert ("restart", "api-proxy") in runtime.calls
    assert config.state_file.read_text(encoding="utf-8") == "fencing\n"

    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)
    assert reconcile(config, "primary") is True
    assert config.state_file.read_text(encoding="utf-8") == "primary\n"


def test_proxy_restart_failure_keeps_primary_fenced_and_bot_stopped(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    config.state_file.write_text("fencing\n", encoding="utf-8")
    runtime = _Runtime(fail_proxy_restart=True)
    readiness_calls = []
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(
        patroni_role_agent,
        "_wait_ready",
        lambda _config: readiness_calls.append("ready"),
    )

    with pytest.raises(subprocess.CalledProcessError):
        reconcile(config, "primary")

    assert readiness_calls == []
    assert "bot" not in runtime.services
    assert config.state_file.read_text(encoding="utf-8") == "fencing\n"


def test_host_nginx_runtime_does_not_attempt_container_proxy_restart(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    runtime = _Runtime("db")
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)

    assert reconcile(config, "primary") is True
    assert ("restart", "api-proxy") not in runtime.calls


def test_standby_recreate_refreshes_proxy_before_committing_fenced_state(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    config.state_file.write_text("primary\n", encoding="utf-8")
    runtime = _Runtime("app-blue", "bot", "api-proxy")
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)

    assert reconcile(config, "standby") is True
    app_start = (
        "up",
        "-d",
        "--no-deps",
        "--force-recreate",
        "app-blue",
    )
    assert runtime.calls.index(app_start) < runtime.calls.index(
        ("restart", "api-proxy")
    )
    assert runtime.services == {"app-blue", "api-proxy"}
    assert config.state_file.read_text(encoding="utf-8") == "standby\n"
