import fcntl
import subprocess
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import patroni_role_agent
from scripts.ha.patroni_role_agent import (
    AgentConfig,
    app_service,
    reconcile,
    role_env,
)


@pytest.fixture(autouse=True)
def _no_host_maintenance_marker(monkeypatch):
    monkeypatch.setattr(
        patroni_role_agent, "read_maintenance_transaction_id", lambda: None
    )


def _config(tmp_path: Path, *, app_service_override: str = "") -> AgentConfig:
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
        app_service=app_service_override,
        primary_systemd_units=(),
        poll_seconds=3,
        promotion_delay_seconds=0,
        ready_attempts=2,
    )


def test_load_config_binds_production_path_to_exact_identity(monkeypatch):
    monkeypatch.setenv("HA_PROJECT_DIR", "/opt/mvn-reserve")
    monkeypatch.delenv("HA_PATRONI_NAME", raising=False)

    config = patroni_role_agent.load_config()

    assert config.patroni_name == "zakup"
    assert config.patroni_scope == "mvn-postgres"
    assert config.patroni_url == "http://127.0.0.1:8008/patroni"

    monkeypatch.setenv("HA_PATRONI_NAME", "mvn-api")
    with pytest.raises(ValueError, match="must be zakup"):
        patroni_role_agent.load_config()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("HA_PATRONI_URL", "http://localhost:8008/patroni", "must be http"),
        ("HA_PATRONI_SCOPE", "other", "must be mvn-postgres"),
        ("HA_PATRONI_MAX_DCS_AGE_SECONDS", "21", "20s bound"),
        ("HA_PROJECT_DIR", "/srv/unknown", "not a reviewed Patroni node"),
    ],
)
def test_load_config_rejects_unreviewed_identity_inputs(
    monkeypatch, name, value, message
):
    for variable in (
        "HA_PATRONI_URL",
        "HA_PATRONI_SCOPE",
        "HA_PATRONI_NAME",
        "HA_PATRONI_MAX_DCS_AGE_SECONDS",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("HA_PROJECT_DIR", "/opt/air-api")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        patroni_role_agent.load_config()


def test_role_env_opens_api_and_singleton_processes_only_on_primary():
    primary_app = role_env("primary", bot_process=False)
    primary_bot = role_env("primary", bot_process=True)
    standby_app = role_env("standby", bot_process=False)
    standby_bot = role_env("standby", bot_process=True)
    externalized_bot = role_env(
        "primary", bot_process=True, bot_enabled=False
    )

    assert "API_READY_ENABLED=true" in primary_app
    assert "SCHEDULER_ENABLED=true" in primary_app
    assert "BOT_ENABLED=false" in primary_app
    assert "API_READY_ENABLED=false" in primary_bot
    assert "SCHEDULER_ENABLED=false" in primary_bot
    assert "BOT_ENABLED=true" in primary_bot
    assert "APP_ROLE=primary" in externalized_bot
    assert "BOT_ENABLED=false" in externalized_bot
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


class _ComposeRuntime:
    def __init__(self, *services: str):
        self.services = set(services)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, _config, *args, check=True, timeout=60):
        del check, timeout
        self.calls.append(args)
        if args[:3] == ("ps", "--status", "running"):
            return SimpleNamespace(returncode=0, stdout="\n".join(sorted(self.services)) + "\n")
        if args[:3] == ("ps", "--all", "--quiet"):
            service = args[-1]
            output = f"id-{service}\n" if service in self.services else ""
            return SimpleNamespace(returncode=0, stdout=output, stderr="")
        if args[0] == "up":
            self.services.add(args[-1])
        elif args[0] in {"rm", "kill", "stop"}:
            self.services.discard(args[-1])
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def _mock_primary_proof(monkeypatch, calls: list[str] | None = None):
    def proof(_config, boundary):
        if calls is not None:
            calls.append(boundary)

    monkeypatch.setattr(patroni_role_agent, "_require_fresh_primary_or_fence", proof)


def test_reconcile_standby_fences_bot_and_apps_before_restarting_safe_app(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    runtime = _ComposeRuntime("app", "bot")
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_cancel_pitr_operations", lambda _config: [])

    assert reconcile(config, "standby") is True
    bot_remove = runtime.calls.index(("rm", "--stop", "--force", "bot"))
    app_start = runtime.calls.index(
        ("up", "-d", "--no-deps", "--force-recreate", "app")
    )
    assert bot_remove < app_start
    assert runtime.services == {"app"}
    assert "API_READY_ENABLED=false" in config.app_role_env.read_text()
    assert config.state_file.read_text() == "standby\n"


def test_standby_fences_docker_and_operations_before_fallible_systemd_query(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    config = AgentConfig(
        **{**config.__dict__, "primary_systemd_units": ("wal.timer",)}
    )
    runtime = _ComposeRuntime("app", "bot")
    events = []

    def units_match(_config, _role):
        events.append(("systemd_query", set(runtime.services)))
        raise subprocess.TimeoutExpired("systemctl", 10)

    def cancel(_config):
        events.append(("cancel_pitr", set(runtime.services)))
        return []

    def reconcile_units(_config, role, *, primary_guard=None):
        assert role == "standby"
        assert primary_guard is None
        units_match(_config, role)

    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_systemd_units_match", units_match)
    monkeypatch.setattr(
        patroni_role_agent, "_reconcile_primary_systemd_units", reconcile_units
    )
    monkeypatch.setattr(patroni_role_agent, "_cancel_pitr_operations", cancel)

    with pytest.raises(RuntimeError, match="standby fence incomplete"):
        reconcile(config, "standby")

    assert events == [
        ("cancel_pitr", set()),
        ("systemd_query", set()),
    ]
    assert runtime.services == set()
    assert "API_READY_ENABLED=false" in config.app_role_env.read_text()
    assert "BOT_ENABLED=false" in config.bot_role_env.read_text()


@pytest.mark.parametrize("inventory_failure", ["error", "timeout"])
def test_standby_fast_fence_precedes_failed_or_hung_compose_inventory(
    tmp_path, monkeypatch, inventory_failure
):
    config = _config(tmp_path, app_service_override="app")
    config.app_role_env.write_text(role_env("primary", bot_process=False))
    config.bot_role_env.write_text(role_env("primary", bot_process=True))
    config.state_file.write_text("primary\n")
    calls: list[tuple[str, ...]] = []

    def compose(_config, *args, **_kwargs):
        calls.append(args)
        if args[:3] == ("ps", "--all", "--quiet"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:3] == ("ps", "--status", "running"):
            if inventory_failure == "timeout":
                raise subprocess.TimeoutExpired("docker compose ps", 60)
            return SimpleNamespace(returncode=1, stdout="", stderr="docker busy")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(patroni_role_agent, "_run_compose", compose)
    monkeypatch.setattr(patroni_role_agent, "_cancel_pitr_operations", lambda _config: [])

    with pytest.raises((RuntimeError, subprocess.TimeoutExpired)):
        reconcile(config, "standby")

    inventory_index = calls.index(("ps", "--status", "running", "--services"))
    removed = [call[-1] for call in calls[:inventory_index] if call[:3] == ("rm", "--stop", "--force")]
    assert removed == ["bot", "app", "app-blue", "app-green"]
    assert config.app_role_env.read_text() == role_env("standby", bot_process=False)
    assert config.bot_role_env.read_text() == role_env("standby", bot_process=True)
    assert config.state_file.read_text() == "fencing\n"


def test_incomplete_standby_fence_persists_retry_state_until_exact_retry_succeeds(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    config.app_role_env.write_text(role_env("primary", bot_process=False))
    config.bot_role_env.write_text(role_env("primary", bot_process=True))
    config.state_file.write_text("standby\n")

    class RetryRuntime:
        def __init__(self):
            self.services = {"app", "bot"}
            self.fail_app = True
            self.calls: list[tuple[str, ...]] = []

        def __call__(self, _config, *args, **_kwargs):
            self.calls.append(args)
            service = args[-1]
            if args[:3] == ("ps", "--status", "running"):
                return SimpleNamespace(
                    returncode=0,
                    stdout="\n".join(sorted(self.services)) + "\n",
                    stderr="",
                )
            if args[:3] == ("ps", "--all", "--quiet"):
                output = f"id-{service}\n" if service in self.services else ""
                return SimpleNamespace(returncode=0, stdout=output, stderr="")
            if service == "app" and self.fail_app and args[0] in {"rm", "kill"}:
                return SimpleNamespace(returncode=1, stdout="", stderr="docker busy")
            if args[0] == "up":
                self.services.add(service)
            elif args[0] in {"rm", "kill", "stop"}:
                self.services.discard(service)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

    runtime = RetryRuntime()
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_cancel_pitr_operations", lambda _config: [])

    with pytest.raises(RuntimeError, match="standby fence incomplete"):
        reconcile(config, "standby")

    assert config.state_file.read_text() == "fencing\n"
    assert runtime.services == {"app"}
    assert config.app_role_env.read_text() == role_env("standby", bot_process=False)

    runtime.fail_app = False
    assert reconcile(config, "standby") is True

    app_fence_attempts = [
        call
        for call in runtime.calls
        if call == ("rm", "--stop", "--force", "app")
    ]
    assert len(app_fence_attempts) == 2
    assert runtime.services == {"app"}
    assert config.state_file.read_text() == "standby\n"


def test_busy_deploy_lock_keeps_fencing_state_until_raced_app_is_recreated(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    config.app_role_env.write_text(role_env("primary", bot_process=False))
    config.bot_role_env.write_text(role_env("primary", bot_process=True))
    config.state_file.write_text("standby\n")
    runtime = _ComposeRuntime("app", "bot")
    lock_attempts = 0

    def flock(_descriptor, operation):
        nonlocal lock_attempts
        if operation & fcntl.LOCK_NB:
            lock_attempts += 1
            if lock_attempts == 1:
                # Model a deploy that parsed the old primary env before the
                # fast fence and creates that container just before deferral.
                runtime.services.add("app")
                raise BlockingIOError

    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_cancel_pitr_operations", lambda _config: [])
    monkeypatch.setattr(patroni_role_agent.fcntl, "flock", flock)

    assert reconcile(config, "standby") is False
    assert config.state_file.read_text() == "fencing\n"
    assert runtime.services == {"app"}

    assert reconcile(config, "standby") is True
    app_fence_attempts = [
        call
        for call in runtime.calls
        if call == ("rm", "--stop", "--force", "app")
    ]
    assert len(app_fence_attempts) == 2
    assert runtime.services == {"app"}
    assert config.app_role_env.read_text() == role_env("standby", bot_process=False)
    assert config.state_file.read_text() == "standby\n"


def test_fast_fence_removes_app_that_appears_during_first_inventory(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    config.app_role_env.write_text(role_env("standby", bot_process=False))
    config.bot_role_env.write_text(role_env("primary", bot_process=True))
    config.state_file.write_text("standby\n")
    runtime = _ComposeRuntime("bot")
    injected = False

    def compose(_config, *args, **kwargs):
        nonlocal injected
        if args[:3] == ("ps", "--status", "running") and not injected:
            injected = True
            runtime.services.add("app")
        return runtime(_config, *args, **kwargs)

    monkeypatch.setattr(patroni_role_agent, "_run_compose", compose)
    monkeypatch.setattr(patroni_role_agent, "_cancel_pitr_operations", lambda _config: [])

    assert reconcile(config, "standby") is True

    app_fence_attempts = [
        call
        for call in runtime.calls
        if call == ("rm", "--stop", "--force", "app")
    ]
    assert len(app_fence_attempts) == 2
    assert runtime.services == {"app"}
    assert config.state_file.read_text() == "standby\n"


def test_app_appearing_at_lock_handoff_is_force_recreated_after_fast_fence(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    config.app_role_env.write_text(role_env("standby", bot_process=False))
    config.bot_role_env.write_text(role_env("primary", bot_process=True))
    config.state_file.write_text("standby\n")
    runtime = _ComposeRuntime("bot")

    def flock(_descriptor, operation):
        if operation & fcntl.LOCK_NB:
            # The deploy parsed the old primary env earlier and publishes the
            # container immediately before yielding the lock to the role agent.
            runtime.services.add("app")

    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_cancel_pitr_operations", lambda _config: [])
    monkeypatch.setattr(patroni_role_agent.fcntl, "flock", flock)

    assert reconcile(config, "standby") is True

    assert (
        "up",
        "-d",
        "--no-deps",
        "--force-recreate",
        "app",
    ) in runtime.calls
    assert runtime.services == {"app"}
    assert config.state_file.read_text() == "standby\n"


def test_reconcile_primary_fences_legacy_bot_without_restarting_it(tmp_path, monkeypatch):
    config = _config(tmp_path, app_service_override="app")
    runtime = _ComposeRuntime("app", "bot")
    events: list[str | tuple[str, ...]] = []

    def compose(_config, *args, **kwargs):
        events.append(args)
        return runtime(_config, *args, **kwargs)

    monkeypatch.setattr(patroni_role_agent, "_run_compose", compose)
    monkeypatch.setattr(
        patroni_role_agent, "_wait_ready", lambda _config: events.append("wait_ready")
    )
    _mock_primary_proof(monkeypatch, events)

    assert reconcile(config, "primary") is True
    assert ("rm", "--stop", "--force", "bot") in events
    assert not any(call[0] == "up" and call[-1] == "bot" for call in runtime.calls)
    assert runtime.services == {"app"}
    assert "BOT_ENABLED=false" in config.bot_role_env.read_text()


def test_systemd_only_repair_is_guarded_and_reported_as_reconcile(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    config = AgentConfig(**{**config.__dict__, "primary_systemd_units": ("wal.timer",)})
    config.app_role_env.write_text(role_env("primary", bot_process=False))
    config.bot_role_env.write_text(
        role_env("primary", bot_process=True, bot_enabled=False)
    )
    config.state_file.write_text("primary\n")
    runtime = _ComposeRuntime("app")
    active = False
    guards: list[str] = []

    def units_match(_config, role):
        return active is (role == "primary")

    def reconcile_units(_config, role, *, primary_guard=None):
        nonlocal active
        if role == "primary":
            assert primary_guard is not None
            primary_guard("wal.timer")
            active = True
        else:
            active = False

    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_systemd_units_match", units_match)
    monkeypatch.setattr(
        patroni_role_agent, "_reconcile_primary_systemd_units", reconcile_units
    )
    _mock_primary_proof(monkeypatch, guards)

    assert reconcile(config, "primary") is True
    assert guards == ["systemd_activation:wal.timer", "primary_postcondition"]
    assert active is True
    assert not any(call[0] == "up" for call in runtime.calls)


def test_valid_maintenance_marker_keeps_pitr_fenced_and_legacy_bot_stopped(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    config = AgentConfig(**{**config.__dict__, "primary_systemd_units": ("wal.timer",)})
    runtime = _ComposeRuntime()
    systemd_active = True
    systemd_roles: list[str] = []

    def units_match(_config, role):
        return systemd_active == (role == "primary")

    def reconcile_units(_config, role, *, primary_guard=None):
        nonlocal systemd_active
        systemd_roles.append(role)
        assert role == "standby"
        assert primary_guard is None
        systemd_active = False

    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(
        patroni_role_agent,
        "read_maintenance_transaction_id",
        lambda: "a" * 32,
    )
    monkeypatch.setattr(
        patroni_role_agent, "_fetch_configured_patroni_role", lambda _config: "primary"
    )
    monkeypatch.setattr(patroni_role_agent, "_systemd_units_match", units_match)
    monkeypatch.setattr(
        patroni_role_agent, "_reconcile_primary_systemd_units", reconcile_units
    )
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)

    assert reconcile(config, "primary") is True
    assert runtime.services == {"app"}
    assert systemd_active is False
    assert systemd_roles and set(systemd_roles) == {"standby"}
    assert config.state_file.read_text() == "primary\n"


def test_unsafe_maintenance_marker_fail_closed_fences_all_runtime(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    runtime = _ComposeRuntime("app", "bot")
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(
        patroni_role_agent,
        "read_maintenance_transaction_id",
        lambda: (_ for _ in ()).throw(RuntimeError("bad owner")),
    )
    monkeypatch.setattr(patroni_role_agent, "_cancel_pitr_operations", lambda _config: [])

    with pytest.raises(RuntimeError, match="unsafe PITR maintenance marker"):
        reconcile(config, "primary")

    assert runtime.services == set()
    assert config.app_role_env.read_text() == role_env("standby", bot_process=False)
    assert config.bot_role_env.read_text() == role_env("standby", bot_process=True)
    assert config.state_file.read_text() == "fencing\n"


def test_marker_appearing_at_pitr_activation_boundary_stops_units_without_stopping_app(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    config = AgentConfig(**{**config.__dict__, "primary_systemd_units": ("wal.timer",)})
    runtime = _ComposeRuntime("app", "bot")
    systemd_active = True
    roles: list[str] = []

    def units_match(_config, role):
        return systemd_active == (role == "primary")

    def reconcile_units(_config, role, *, primary_guard=None):
        nonlocal systemd_active
        roles.append(role)
        assert role == "standby"
        systemd_active = False

    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(
        patroni_role_agent,
        "read_maintenance_transaction_id",
        lambda: "b" * 32,
    )
    monkeypatch.setattr(
        patroni_role_agent, "_fetch_configured_patroni_role", lambda _config: "primary"
    )
    monkeypatch.setattr(patroni_role_agent, "_systemd_units_match", units_match)
    monkeypatch.setattr(
        patroni_role_agent, "_reconcile_primary_systemd_units", reconcile_units
    )

    with pytest.raises(RuntimeError, match="maintenance marker appeared"):
        patroni_role_agent._guard_pitr_activation(config, "wal.timer")

    assert systemd_active is False
    assert roles == ["standby"]
    assert runtime.services == {"app", "bot"}


def test_reconcile_does_not_recreate_services_when_compose_ps_fails(
    tmp_path, monkeypatch
):
    config = _config(tmp_path, app_service_override="app")
    calls: list[tuple[str, ...]] = []

    def fake_compose(_config, *args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout="", stderr="docker busy")

    monkeypatch.setattr(patroni_role_agent, "_run_compose", fake_compose)

    with pytest.raises(RuntimeError, match="docker busy"):
        reconcile(config, "primary")
    assert calls == [("ps", "--status", "running", "--services")]


def test_network_error_is_treated_as_standby(tmp_path, monkeypatch):
    config = _config(tmp_path)
    roles: list[str] = []
    monkeypatch.setattr(
        patroni_role_agent,
        "_fetch_configured_patroni_role",
        lambda _config: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    monkeypatch.setattr(
        patroni_role_agent,
        "reconcile",
        lambda _config, role: roles.append(role),
    )

    assert patroni_role_agent.run(config, once=True) == 0
    assert roles == ["standby"]


PRIMARY_ACTIVATION_BOUNDARIES = [
    "primary_app_env",
    "app_activation",
    "systemd_activation:wal.timer",
    "systemd_activation:base.timer",
    "primary_postcondition",
    "primary_state",
]


@pytest.mark.parametrize("flip_boundary", PRIMARY_ACTIVATION_BOUNDARIES)
def test_primary_flip_at_each_activation_boundary_immediately_fences_runtime(
    tmp_path, monkeypatch, flip_boundary
):
    config = _config(tmp_path, app_service_override="app")
    config = AgentConfig(
        **{
            **config.__dict__,
            "primary_systemd_units": ("wal.timer", "base.timer"),
        }
    )
    config.app_role_env.write_text(role_env("standby", bot_process=False))
    config.bot_role_env.write_text(
        role_env("primary", bot_process=True, bot_enabled=False)
    )
    config.state_file.write_text("standby\n")
    runtime = _ComposeRuntime()
    systemd_active = False
    probe_index = 0
    expected_index = PRIMARY_ACTIVATION_BOUNDARIES.index(flip_boundary)

    def fetch_role(_config):
        nonlocal probe_index
        role = "standby" if probe_index == expected_index else "primary"
        probe_index += 1
        return role

    def units_match(_config, role):
        return systemd_active is (role == "primary")

    def reconcile_units(_config, role, *, primary_guard=None):
        nonlocal systemd_active
        if role == "primary":
            assert primary_guard is not None
            for unit in config.primary_systemd_units:
                primary_guard(unit)
                systemd_active = True
        else:
            systemd_active = False

    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_fetch_configured_patroni_role", fetch_role)
    monkeypatch.setattr(patroni_role_agent, "_systemd_units_match", units_match)
    monkeypatch.setattr(
        patroni_role_agent, "_reconcile_primary_systemd_units", reconcile_units
    )
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)
    monkeypatch.setattr(patroni_role_agent, "_cancel_pitr_operations", lambda _config: [])

    with pytest.raises(RuntimeError, match=flip_boundary):
        reconcile(config, "primary")

    assert runtime.services == set()
    assert systemd_active is False
    assert config.app_role_env.read_text() == role_env("standby", bot_process=False)
    assert config.bot_role_env.read_text() == role_env("standby", bot_process=True)
    assert config.state_file.read_text() == "fencing\n"


def test_network_loss_at_activation_boundary_also_fences(tmp_path, monkeypatch):
    config = _config(tmp_path, app_service_override="app")
    config.app_role_env.write_text(role_env("primary", bot_process=False))
    config.bot_role_env.write_text(
        role_env("primary", bot_process=True, bot_enabled=False)
    )
    config.state_file.write_text("primary\n")
    runtime = _ComposeRuntime()
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)
    monkeypatch.setattr(patroni_role_agent, "_cancel_pitr_operations", lambda _config: [])
    monkeypatch.setattr(
        patroni_role_agent,
        "_fetch_configured_patroni_role",
        lambda _config: (_ for _ in ()).throw(urllib.error.URLError("lost DCS")),
    )

    with pytest.raises(RuntimeError, match="app_activation"):
        reconcile(config, "primary")

    assert runtime.services == set()
    assert config.state_file.read_text() == "fencing\n"
