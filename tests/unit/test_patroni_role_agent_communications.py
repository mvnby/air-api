import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import patroni_role_agent
from scripts.ha.patroni_local_identity import COMMUNICATIONS_WORKER_SERVICE
from scripts.ha.patroni_role_agent import AgentConfig


@pytest.fixture(autouse=True)
def _safe_host_contracts(monkeypatch):
    monkeypatch.setattr(
        patroni_role_agent,
        "read_maintenance_transaction_id",
        lambda: None,
    )
    monkeypatch.setattr(
        patroni_role_agent,
        "_cancel_pitr_operations",
        lambda _config: [],
    )
    monkeypatch.setattr(
        patroni_role_agent,
        "_run_docker",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="",
        ),
    )


def _config(tmp_path: Path) -> AgentConfig:
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
        app_service="app",
        primary_systemd_units=(),
        poll_seconds=3,
        promotion_delay_seconds=0,
        ready_attempts=2,
    )


class _ComposeRuntime:
    def __init__(
        self,
        events: list[object],
        *,
        defined_services: set[str],
        running_services: set[str],
        worker_start_succeeds: bool = True,
        worker_role: str | None = None,
        worker_role_on_start: str | None = None,
        definition_error: Exception | None = None,
        role_probe_error: Exception | None = None,
        worker_enabled: bool = False,
        worker_allow_all: bool = False,
    ):
        self.events = events
        self.defined_services = set(defined_services)
        self.running_services = set(running_services)
        self.worker_start_succeeds = worker_start_succeeds
        self.worker_role = worker_role
        self.worker_role_on_start = worker_role_on_start
        self.definition_error = definition_error
        self.role_probe_error = role_probe_error
        self.worker_enabled = worker_enabled
        self.worker_allow_all = worker_allow_all

    def __call__(self, config, *args, **_kwargs):
        self.events.append(("compose", args))
        if args == ("config", "--services"):
            if self.definition_error is not None:
                raise self.definition_error
            return SimpleNamespace(
                returncode=0,
                stdout="\n".join(sorted(self.defined_services)) + "\n",
                stderr="",
            )
        if args[:3] == ("ps", "--status", "running"):
            stdout = "\n".join(
                json.dumps(
                    {
                        "Service": service,
                        "Labels": "com.docker.compose.oneoff=False",
                    }
                )
                for service in sorted(self.running_services)
            )
            return SimpleNamespace(
                returncode=0,
                stdout=stdout + ("\n" if stdout else ""),
                stderr="",
            )
        if args[:3] == ("ps", "--all", "--quiet"):
            service = args[-1]
            container_id = (
                f"id-{service}\n" if service in self.running_services else ""
            )
            return SimpleNamespace(returncode=0, stdout=container_id, stderr="")
        if args[:3] == ("exec", "-T", COMMUNICATIONS_WORKER_SERVICE):
            if self.role_probe_error is not None:
                raise self.role_probe_error
            expected_role = args[-1]
            return SimpleNamespace(
                returncode=(
                    0
                    if (
                        self.worker_role == expected_role
                        and not self.worker_enabled
                        and not self.worker_allow_all
                    )
                    else 1
                ),
                stdout="",
                stderr="",
            )
        if args[0] == "up":
            service = args[-1]
            if service != COMMUNICATIONS_WORKER_SERVICE or self.worker_start_succeeds:
                self.running_services.add(service)
                if service == COMMUNICATIONS_WORKER_SERVICE:
                    self.worker_role = (
                        self.worker_role_on_start
                        or next(
                            line.split("=", 1)[1]
                            for line in config.app_role_env.read_text(
                                encoding="utf-8"
                            ).splitlines()
                            if line.startswith("APP_ROLE=")
                        )
                    )
                    self.worker_enabled = False
                    self.worker_allow_all = False
        elif args[0] in {"rm", "kill", "stop"}:
            self.running_services.discard(args[-1])
            if args[-1] == COMMUNICATIONS_WORKER_SERVICE:
                self.worker_role = None
                self.worker_enabled = False
                self.worker_allow_all = False
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def docker(self, *args, **_kwargs):
        self.events.append(("docker", args))
        if args[:2] == ("ps", "--all"):
            container_id = (
                "c" * 12 + "\n"
                if COMMUNICATIONS_WORKER_SERVICE in self.running_services
                else ""
            )
            return SimpleNamespace(returncode=0, stdout=container_id, stderr="")
        if args[0] == "rm":
            self.running_services.discard(COMMUNICATIONS_WORKER_SERVICE)
            self.worker_role = None
            self.worker_enabled = False
            self.worker_allow_all = False
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def _command_index(events: list[object], command: tuple[str, ...]) -> int:
    return events.index(("compose", command))


def _docker_command_index(events: list[object], command: tuple[str, ...]) -> int:
    return events.index(("docker", command))


def test_worker_is_fenced_then_recreated_across_primary_standby_primary(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    config.app_role_env.write_text(
        patroni_role_agent.role_env("primary", bot_process=False),
        encoding="utf-8",
    )
    config.bot_role_env.write_text(
        patroni_role_agent.role_env(
            "primary",
            bot_process=True,
            bot_enabled=False,
        ),
        encoding="utf-8",
    )
    config.state_file.write_text("primary\n", encoding="utf-8")
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        running_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        worker_role="primary",
    )
    real_atomic_write = patroni_role_agent._atomic_write

    def atomic_write(path, content, **kwargs):
        events.append(("write", path.name, content.splitlines()[0]))
        real_atomic_write(path, content, **kwargs)

    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(patroni_role_agent, "_atomic_write", atomic_write)
    monkeypatch.setattr(
        patroni_role_agent,
        "_systemd_units_match",
        lambda _config, role: events.append(("systemd_check", role)) or True,
    )
    monkeypatch.setattr(
        patroni_role_agent,
        "_reconcile_primary_systemd_units",
        lambda _config, role, **_kwargs: events.append(("systemd_reconcile", role)),
    )
    monkeypatch.setattr(
        patroni_role_agent.fcntl,
        "flock",
        lambda _lock, _operation: events.append("deploy_lock"),
    )

    assert patroni_role_agent.reconcile(config, "standby") is True

    worker_stop = _docker_command_index(
        events,
        ("stop", "--timeout", "10", "c" * 12),
    )
    standby_env = events.index(
        ("write", ".ha-app-role.env", "APP_ROLE=standby")
    )
    deploy_lock = events.index("deploy_lock")
    worker_recreate = _command_index(
        events,
        (
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            COMMUNICATIONS_WORKER_SERVICE,
        ),
    )
    first_systemd = next(
        index
        for index, event in enumerate(events)
        if isinstance(event, tuple) and event[0].startswith("systemd_")
    )
    assert worker_stop < standby_env < first_systemd < deploy_lock < worker_recreate
    assert runtime.running_services == {"app", COMMUNICATIONS_WORKER_SERVICE}
    assert config.state_file.read_text(encoding="utf-8") == "standby\n"

    events.clear()
    proofs: list[str] = []

    def primary_proof(_config, boundary):
        proofs.append(boundary)
        events.append(("primary_proof", boundary))

    monkeypatch.setattr(
        patroni_role_agent,
        "_require_fresh_primary_or_fence",
        primary_proof,
    )
    monkeypatch.setattr(
        patroni_role_agent,
        "_wait_ready",
        lambda _config: events.append("app_ready"),
    )

    assert patroni_role_agent.reconcile(config, "primary") is True

    app_recreate = _command_index(
        events,
        ("up", "-d", "--no-deps", "--force-recreate", "app"),
    )
    worker_recreate = _command_index(
        events,
        (
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            COMMUNICATIONS_WORKER_SERVICE,
        ),
    )
    app_ready = events.index("app_ready")
    worker_proof = events.index(
        ("primary_proof", "communications_worker_activation")
    )
    assert app_recreate < app_ready < worker_proof < worker_recreate
    assert "primary_app_env" in proofs
    assert "primary_postcondition" in proofs
    assert runtime.running_services == {"app", COMMUNICATIONS_WORKER_SERVICE}
    assert config.state_file.read_text(encoding="utf-8") == "primary\n"


@pytest.mark.parametrize("role", ["primary", "standby"])
def test_old_compose_without_worker_remains_rolling_compatible(
    tmp_path, monkeypatch, role
):
    config = _config(tmp_path)
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app"},
        running_services={"app"},
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(
        patroni_role_agent,
        "_require_fresh_primary_or_fence",
        lambda _config, _boundary: None,
    )
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)

    assert patroni_role_agent.reconcile(config, role) is True
    assert not any(
        isinstance(event, tuple)
        and event[0] == "compose"
        and event[1][-1:] == (COMMUNICATIONS_WORKER_SERVICE,)
        for event in events
    )
    assert runtime.running_services == {"app"}


def test_old_canonical_ignores_candidate_worker_until_compose_promotion(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    config.app_role_env.write_text(
        patroni_role_agent.role_env("primary", bot_process=False),
        encoding="utf-8",
    )
    config.bot_role_env.write_text(
        patroni_role_agent.role_env(
            "primary",
            bot_process=True,
            bot_enabled=False,
        ),
        encoding="utf-8",
    )
    config.state_file.write_text("primary\n", encoding="utf-8")
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app"},
        running_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        worker_role="primary",
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(
        patroni_role_agent,
        "_systemd_units_match",
        lambda *_args: True,
    )

    assert patroni_role_agent.reconcile(config, "primary") is False
    assert COMMUNICATIONS_WORKER_SERVICE in runtime.running_services
    assert not any(
        event[0] == "docker" for event in events if isinstance(event, tuple)
    )

    runtime.defined_services.add(COMMUNICATIONS_WORKER_SERVICE)
    events.clear()

    assert patroni_role_agent.reconcile(config, "primary") is False
    assert COMMUNICATIONS_WORKER_SERVICE in runtime.running_services
    assert any(
        event[0] == "compose"
        and event[1][:3] == ("exec", "-T", COMMUNICATIONS_WORKER_SERVICE)
        and event[1][-1] == "primary"
        for event in events
        if isinstance(event, tuple)
    )
    assert not any(
        event[0] == "docker" for event in events if isinstance(event, tuple)
    )


def test_defined_worker_must_be_running_at_final_postcondition(tmp_path, monkeypatch):
    config = _config(tmp_path)
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        running_services={"app"},
        worker_start_succeeds=False,
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(
        patroni_role_agent,
        "_require_fresh_primary_or_fence",
        lambda _config, _boundary: None,
    )
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)

    with pytest.raises(
        RuntimeError,
        match="primary communications worker role postcondition failed",
    ):
        patroni_role_agent.reconcile(config, "primary")


def test_defined_worker_must_have_expected_role_at_final_postcondition(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        running_services={"app"},
        worker_role_on_start="standby",
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(
        patroni_role_agent,
        "_require_fresh_primary_or_fence",
        lambda _config, _boundary: None,
    )
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)

    with pytest.raises(
        RuntimeError,
        match="primary communications worker role postcondition failed",
    ):
        patroni_role_agent.reconcile(config, "primary")
    assert COMMUNICATIONS_WORKER_SERVICE not in runtime.running_services


def test_stale_running_worker_role_fences_all_side_effect_owners_before_systemd(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    config.app_role_env.write_text(
        patroni_role_agent.role_env("standby", bot_process=False),
        encoding="utf-8",
    )
    config.bot_role_env.write_text(
        patroni_role_agent.role_env(
            "standby",
            bot_process=True,
            bot_enabled=False,
        ),
        encoding="utf-8",
    )
    config.state_file.write_text("standby\n", encoding="utf-8")
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", "bot", COMMUNICATIONS_WORKER_SERVICE},
        running_services={"app", "bot", COMMUNICATIONS_WORKER_SERVICE},
        worker_role="primary",
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(
        patroni_role_agent,
        "_systemd_units_match",
        lambda _config, role: events.append(("systemd_check", role)) or True,
    )
    monkeypatch.setattr(
        patroni_role_agent,
        "_reconcile_primary_systemd_units",
        lambda _config, role, **_kwargs: events.append(("systemd_reconcile", role)),
    )

    assert patroni_role_agent.reconcile(config, "standby") is True

    worker_stop = _docker_command_index(
        events,
        ("stop", "--timeout", "10", "c" * 12),
    )
    app_stop = _command_index(
        events,
        ("rm", "--stop", "--force", "app"),
    )
    bot_stop = _command_index(
        events,
        ("rm", "--stop", "--force", "bot"),
    )
    first_systemd = next(
        index
        for index, event in enumerate(events)
        if isinstance(event, tuple) and event[0].startswith("systemd_")
    )
    assert max(worker_stop, app_stop, bot_stop) < first_systemd
    assert runtime.running_services == {"app", COMMUNICATIONS_WORKER_SERVICE}
    assert runtime.worker_role == "standby"
    assert config.state_file.read_text(encoding="utf-8") == "standby\n"


def test_definition_probe_failure_fences_labeled_worker_before_later_checks(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    config.app_role_env.write_text(
        patroni_role_agent.role_env("standby", bot_process=False),
        encoding="utf-8",
    )
    config.bot_role_env.write_text(
        patroni_role_agent.role_env(
            "standby",
            bot_process=True,
            bot_enabled=False,
        ),
        encoding="utf-8",
    )
    config.state_file.write_text("standby\n", encoding="utf-8")
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        running_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        worker_role="primary",
        definition_error=subprocess.TimeoutExpired("compose config", 20),
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(
        patroni_role_agent,
        "_systemd_units_match",
        lambda *_args: events.append("systemd_check") or True,
    )
    monkeypatch.setattr(
        patroni_role_agent.fcntl,
        "flock",
        lambda *_args: events.append("deploy_lock"),
    )

    with pytest.raises(subprocess.TimeoutExpired):
        patroni_role_agent.reconcile(config, "standby")

    worker_remove = _docker_command_index(
        events,
        ("rm", "--force", "c" * 12),
    )
    assert worker_remove < len(events)
    assert "systemd_check" not in events
    assert "deploy_lock" not in events
    assert COMMUNICATIONS_WORKER_SERVICE not in runtime.running_services


def test_role_probe_timeout_fences_worker_before_primary_later_checks(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    config.app_role_env.write_text(
        patroni_role_agent.role_env("primary", bot_process=False),
        encoding="utf-8",
    )
    config.bot_role_env.write_text(
        patroni_role_agent.role_env(
            "primary",
            bot_process=True,
            bot_enabled=False,
        ),
        encoding="utf-8",
    )
    config.state_file.write_text("primary\n", encoding="utf-8")
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        running_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        worker_role="primary",
        role_probe_error=subprocess.TimeoutExpired("worker role probe", 10),
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(
        patroni_role_agent,
        "_systemd_units_match",
        lambda *_args: events.append("systemd_check") or True,
    )
    monkeypatch.setattr(
        patroni_role_agent,
        "_require_fresh_primary_or_fence",
        lambda *_args: None,
    )
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)

    with pytest.raises(
        RuntimeError,
        match="primary communications worker role postcondition failed",
    ):
        patroni_role_agent.reconcile(config, "primary")

    first_worker_remove = _docker_command_index(
        events,
        ("rm", "--force", "c" * 12),
    )
    first_systemd = events.index("systemd_check")
    assert first_worker_remove < first_systemd
    assert COMMUNICATIONS_WORKER_SERVICE not in runtime.running_services


@pytest.mark.parametrize(
    "drift",
    [
        {"worker_enabled": True},
        {"worker_allow_all": True},
    ],
)
def test_delivery_gate_drift_fences_and_recreates_worker(
    tmp_path, monkeypatch, capsys, drift
):
    config = _config(tmp_path)
    config.app_role_env.write_text(
        patroni_role_agent.role_env("primary", bot_process=False),
        encoding="utf-8",
    )
    config.bot_role_env.write_text(
        patroni_role_agent.role_env(
            "primary",
            bot_process=True,
            bot_enabled=False,
        ),
        encoding="utf-8",
    )
    config.state_file.write_text("primary\n", encoding="utf-8")
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        running_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        worker_role="primary",
        **drift,
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(
        patroni_role_agent,
        "_systemd_units_match",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        patroni_role_agent,
        "_require_fresh_primary_or_fence",
        lambda *_args: None,
    )
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)
    monkeypatch.setattr(
        patroni_role_agent,
        "_fetch_configured_patroni_role",
        lambda _config: "primary",
    )

    assert patroni_role_agent.run(config, once=True) == 0

    worker_remove = _docker_command_index(
        events,
        ("rm", "--force", "c" * 12),
    )
    worker_recreate = _command_index(
        events,
        (
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            COMMUNICATIONS_WORKER_SERVICE,
        ),
    )
    assert worker_remove < worker_recreate
    assert runtime.worker_role == "primary"
    assert runtime.worker_enabled is False
    assert runtime.worker_allow_all is False
    output = capsys.readouterr().out.splitlines()
    assert len(output) == 2
    assert output[0].startswith(
        "patroni_role_agent_status=reconciled role=primary "
    )
    assert "communications_worker_role_drift" in output[0]
    assert "recreate_communications_worker" in output[0]
    assert output[1] == "patroni_role_agent_once_status=verified role=primary"
