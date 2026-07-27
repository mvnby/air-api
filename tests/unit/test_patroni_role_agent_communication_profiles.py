from types import SimpleNamespace

import pytest

from scripts.ha import patroni_role_agent
from scripts.ha.patroni_local_identity import COMMUNICATIONS_WORKER_SERVICE
from tests.unit.test_patroni_role_agent_communications import (
    _ComposeRuntime,
    _command_index,
    _config,
    _docker_command_index,
)


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


def _write_primary_state(config):
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


def test_invalid_mixed_delivery_gate_fences_and_recreates_worker(
    tmp_path, monkeypatch, capsys
):
    config = _config(tmp_path)
    _write_primary_state(config)
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        running_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        worker_role="primary",
        worker_allow_all=True,
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(patroni_role_agent, "_systemd_units_match", lambda *_args: True)
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


@pytest.mark.parametrize(
    ("role", "worker_enabled", "worker_allow_all"),
    [
        ("primary", True, False),
        ("primary", True, True),
        ("standby", True, False),
        ("standby", True, True),
    ],
)
def test_reviewed_candidate_profile_is_not_fenced_while_deploy_lock_is_busy(
    tmp_path,
    monkeypatch,
    capsys,
    role,
    worker_enabled,
    worker_allow_all,
):
    config = _config(tmp_path)
    config.app_role_env.write_text(
        patroni_role_agent.role_env(role, bot_process=False),
        encoding="utf-8",
    )
    config.bot_role_env.write_text(
        patroni_role_agent.role_env(
            role,
            bot_process=True,
            bot_enabled=False,
        ),
        encoding="utf-8",
    )
    config.state_file.write_text(f"{role}\n", encoding="utf-8")
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        running_services={COMMUNICATIONS_WORKER_SERVICE},
        worker_role=role,
        worker_enabled=worker_enabled,
        worker_allow_all=worker_allow_all,
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(patroni_role_agent, "_systemd_units_match", lambda *_args: True)

    def lock_busy(*_args):
        events.append("deploy_lock_busy")
        raise BlockingIOError

    monkeypatch.setattr(patroni_role_agent.fcntl, "flock", lock_busy)

    assert patroni_role_agent.reconcile(config, role) is None
    assert COMMUNICATIONS_WORKER_SERVICE in runtime.running_services
    assert "deploy_lock_busy" in events
    assert not any(
        isinstance(event, tuple) and event[0] == "docker"
        for event in events
    )
    assert capsys.readouterr().out.strip() == (
        "patroni_role_agent_status=deferred reason=deployment_lock_busy"
    )


@pytest.mark.parametrize(
    ("worker_enabled", "worker_allow_all"),
    [(True, False), (True, True)],
)
def test_reviewed_but_noncanonical_profile_reconciles_after_deploy_window(
    tmp_path,
    monkeypatch,
    capsys,
    worker_enabled,
    worker_allow_all,
):
    config = _config(tmp_path)
    _write_primary_state(config)
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        running_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        worker_role="primary",
        worker_enabled=worker_enabled,
        worker_allow_all=worker_allow_all,
        canonical_worker_enabled=False,
        canonical_worker_allow_all=False,
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(patroni_role_agent, "_systemd_units_match", lambda *_args: True)
    monkeypatch.setattr(
        patroni_role_agent,
        "_require_fresh_primary_or_fence",
        lambda *_args: None,
    )
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)
    monkeypatch.setattr(
        patroni_role_agent.fcntl,
        "flock",
        lambda *_args: events.append("deploy_lock_acquired"),
    )

    assert patroni_role_agent.reconcile(config, "primary") is True
    assert runtime.worker_enabled is False
    assert runtime.worker_allow_all is False
    assert "deploy_lock_acquired" in events
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
    assert events.index("deploy_lock_acquired") < worker_recreate
    assert not any(
        isinstance(event, tuple) and event[0] == "docker"
        for event in events
    )
    output = capsys.readouterr().out.strip()
    assert "communications_worker_profile_drift" in output
    assert "recreate_communications_worker" in output


def test_invalid_mixed_profile_is_fenced_before_busy_deploy_lock(
    tmp_path,
    monkeypatch,
    capsys,
):
    config = _config(tmp_path)
    _write_primary_state(config)
    events: list[object] = []
    runtime = _ComposeRuntime(
        events,
        defined_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        running_services={"app", COMMUNICATIONS_WORKER_SERVICE},
        worker_role="primary",
        worker_enabled=False,
        worker_allow_all=True,
    )
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
    monkeypatch.setattr(patroni_role_agent, "_systemd_units_match", lambda *_args: True)

    def lock_busy(*_args):
        events.append("deploy_lock_busy")
        raise BlockingIOError

    monkeypatch.setattr(patroni_role_agent.fcntl, "flock", lock_busy)

    assert patroni_role_agent.reconcile(config, "primary") is None
    worker_stop = _docker_command_index(
        events,
        ("stop", "--timeout", "10", "c" * 12),
    )
    assert worker_stop < events.index("deploy_lock_busy")
    assert COMMUNICATIONS_WORKER_SERVICE not in runtime.running_services
    assert capsys.readouterr().out.strip() == (
        "patroni_role_agent_status=deferred reason=deployment_lock_busy"
    )
