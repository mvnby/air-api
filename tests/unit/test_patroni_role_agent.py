from pathlib import Path
from types import SimpleNamespace

from scripts.ha import patroni_role_agent
from scripts.ha.patroni_role_agent import AgentConfig, app_service, reconcile, role_env


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
        poll_seconds=3,
        promotion_delay_seconds=0,
        ready_attempts=2,
    )


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
