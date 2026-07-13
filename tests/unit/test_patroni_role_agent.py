from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import patroni_role_agent
from scripts.ha.patroni_role_agent import (
    AgentConfig,
    app_service,
    fetch_patroni_role,
    reconcile,
    role_env,
)


def _config(tmp_path: Path, *, app_service_override: str = "") -> AgentConfig:
    return AgentConfig(
        project_dir=tmp_path,
        compose_file="compose.yml",
        patroni_url="http://127.0.0.1:8008/patroni",
        ready_url="http://127.0.0.1:18080/api/ready",
        app_role_env=tmp_path / ".ha-app-role.env",
        bot_role_env=tmp_path / ".ha-bot-role.env",
        state_file=tmp_path / ".ha-runtime-role",
        deploy_lock=tmp_path / ".deploy.lock",
        active_slot_file=tmp_path / ".active-api-slot",
        app_service=app_service_override,
        primary_systemd_units=(),
        poll_seconds=3,
        promotion_delay_seconds=0,
        ready_attempts=2,
    )


class _PatroniResponse:
    def __init__(self, payload: str):
        self.payload = payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.payload


@pytest.mark.parametrize(
    ("reported_role", "expected_role"),
    [("leader", "primary"), ("primary", "primary"), ("replica", "standby")],
)
def test_fetch_patroni_role_uses_explicit_role_whitelist(
    monkeypatch, reported_role, expected_role
):
    response = _PatroniResponse(
        f'{{"state":"running","role":"{reported_role}"}}'
    )
    monkeypatch.setattr(
        patroni_role_agent.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: response,
    )

    assert fetch_patroni_role("http://patroni.invalid/patroni") == expected_role


def test_fetch_patroni_role_rejects_unknown_running_role(monkeypatch):
    response = _PatroniResponse('{"state":"running","role":"mystery"}')
    monkeypatch.setattr(
        patroni_role_agent.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(ValueError, match="unsupported Patroni role: mystery"):
        fetch_patroni_role("http://patroni.invalid/patroni")


def test_role_env_opens_api_and_singleton_processes_only_on_primary():
    primary_app = role_env("primary", bot_process=False)
    primary_bot = role_env("primary", bot_process=True)
    standby_app = role_env("standby", bot_process=False)
    standby_bot = role_env("standby", bot_process=True)

    assert "API_READY_ENABLED=true" in primary_app
    assert "SCHEDULER_ENABLED=true" in primary_app
    assert "BOT_ENABLED=false" in primary_app
    assert "API_READY_ENABLED=false" in primary_bot
    assert "SCHEDULER_ENABLED=false" in primary_bot
    assert "BOT_ENABLED=true" in primary_bot
    assert "API_READY_ENABLED=false" in standby_app
    assert "SCHEDULER_ENABLED=false" in standby_app
    assert "BOT_ENABLED=false" in standby_bot
    assert "DB_BOOTSTRAP_ENABLED=false" in standby_app
    assert "MAIL_IMAP_AUTO_IMPORT_ENABLED=false" in standby_app
    assert "CLOUDFLARE_PURGE_ENABLED=false" in standby_app
    assert "MAIL_IMAP_AUTO_IMPORT_ENABLED" not in primary_app


def test_app_service_follows_blue_green_slot(tmp_path):
    config = _config(tmp_path)

    assert app_service(config) == "app"
    config.active_slot_file.write_text("blue\n", encoding="utf-8")
    assert app_service(config) == "app-blue"
    config.active_slot_file.write_text("green\n", encoding="utf-8")
    assert app_service(config) == "app-green"


def test_app_service_override_supports_in_place_standby(tmp_path):
    assert app_service(_config(tmp_path, app_service_override="app")) == "app"


def test_reconcile_standby_stops_bot_before_recreating_app(tmp_path, monkeypatch):
    config = _config(tmp_path, app_service_override="app")
    calls: list[tuple[str, ...]] = []

    def fake_compose(_config, *args, check=True):
        calls.append(args)
        if args[:3] == ("ps", "--status", "running"):
            return SimpleNamespace(returncode=0, stdout="app\nbot\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(patroni_role_agent, "_run_compose", fake_compose)

    assert reconcile(config, "standby") is True
    assert calls[-2] == ("stop", "bot")
    assert calls[-1] == ("up", "-d", "--no-deps", "--force-recreate", "app")
    assert "API_READY_ENABLED=false" in config.app_role_env.read_text(encoding="utf-8")
    assert config.state_file.read_text(encoding="utf-8") == "standby\n"


def test_reconcile_primary_waits_for_ready_before_starting_bot(tmp_path, monkeypatch):
    config = _config(tmp_path, app_service_override="app")
    calls: list[tuple[str, ...] | tuple[str]] = []

    def fake_compose(_config, *args, check=True):
        calls.append(args)
        if args[:3] == ("ps", "--status", "running"):
            return SimpleNamespace(returncode=0, stdout="app\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(patroni_role_agent, "_run_compose", fake_compose)
    monkeypatch.setattr(
        patroni_role_agent,
        "_wait_ready",
        lambda _config: calls.append(("wait-ready",)),
    )

    assert reconcile(config, "primary") is True
    assert calls[-3] == ("up", "-d", "--no-deps", "--force-recreate", "app")
    assert calls[-2] == ("wait-ready",)
    assert calls[-1] == ("up", "-d", "--no-deps", "--force-recreate", "bot")
    assert "SCHEDULER_ENABLED=true" in config.app_role_env.read_text(encoding="utf-8")
    assert "BOT_ENABLED=true" in config.bot_role_env.read_text(encoding="utf-8")


def test_primary_only_systemd_units_follow_role_without_recreating_matching_runtime(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    config = AgentConfig(**{**config.__dict__, "primary_systemd_units": ("wal.timer",)})
    config.app_role_env.write_text(role_env("primary", bot_process=False), encoding="utf-8")
    config.bot_role_env.write_text(role_env("primary", bot_process=True), encoding="utf-8")
    config.state_file.write_text("primary\n", encoding="utf-8")
    compose_calls: list[tuple[str, ...]] = []
    systemctl_calls: list[tuple[str, ...]] = []

    def fake_compose(_config, *args, check=True):
        compose_calls.append(args)
        return SimpleNamespace(returncode=0, stdout="app\nbot\n")

    def fake_run(command, **_kwargs):
        systemctl_calls.append(tuple(command))
        if command[1:3] == ["is-active", "--quiet"]:
            return SimpleNamespace(returncode=3, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(patroni_role_agent, "_run_compose", fake_compose)
    monkeypatch.setattr(patroni_role_agent.subprocess, "run", fake_run)

    assert reconcile(config, "primary") is False
    assert compose_calls == [("ps", "--status", "running", "--services")]
    assert systemctl_calls == [
        ("systemctl", "is-active", "--quiet", "wal.timer"),
        ("systemctl", "start", "wal.timer"),
    ]


def test_reconcile_primary_starts_missing_bot_without_recreating_app(
    tmp_path, monkeypatch, capsys
):
    config = _config(tmp_path, app_service_override="app")
    config.app_role_env.write_text(role_env("primary", bot_process=False), encoding="utf-8")
    config.bot_role_env.write_text(role_env("primary", bot_process=True), encoding="utf-8")
    config.state_file.write_text("primary\n", encoding="utf-8")
    calls: list[tuple[str, ...] | tuple[str]] = []

    def fake_compose(_config, *args, check=True):
        calls.append(args)
        if args[:3] == ("ps", "--status", "running"):
            return SimpleNamespace(returncode=0, stdout="app\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(patroni_role_agent, "_run_compose", fake_compose)
    monkeypatch.setattr(
        patroni_role_agent,
        "_wait_ready",
        lambda _config: calls.append(("wait-ready",)),
    )

    assert reconcile(config, "primary") is True
    assert calls == [
        ("ps", "--status", "running", "--services"),
        ("wait-ready",),
        ("up", "-d", "--no-deps", "bot"),
    ]
    output = capsys.readouterr().out
    assert "reasons=bot_not_running" in output
    assert "actions=wait_ready,start_bot" in output


def test_reconcile_does_not_recreate_services_when_compose_ps_fails(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    calls: list[tuple[str, ...]] = []

    def fake_compose(_config, *args, check=True):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout="", stderr="docker busy")

    monkeypatch.setattr(patroni_role_agent, "_run_compose", fake_compose)

    with pytest.raises(RuntimeError, match="docker busy"):
        reconcile(config, "primary")

    assert calls == [("ps", "--status", "running", "--services")]
