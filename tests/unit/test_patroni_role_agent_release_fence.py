import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import patroni_role_agent
from scripts.ha.patroni_local_identity import COMMUNICATIONS_WORKER_SERVICE
from scripts.ha.patroni_role_agent_config import (
    COMMUNICATIONS_WORKER_RELEASE_FENCE_BASENAME,
    AgentConfig,
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


def _prime_role(config: AgentConfig, role: str) -> None:
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


class _Runtime:
    container_id = "d" * 12

    def __init__(self, *, worker_running: bool):
        self.services = {"app"}
        if worker_running:
            self.services.add(COMMUNICATIONS_WORKER_SERVICE)
        self.events: list[tuple[str, tuple[str, ...]]] = []

    def compose(self, _config, *args, **_kwargs):
        self.events.append(("compose", args))
        if args == ("config", "--services"):
            return SimpleNamespace(
                returncode=0,
                stdout=f"app\n{COMMUNICATIONS_WORKER_SERVICE}\n",
                stderr="",
            )
        if args == ("config", "--format", "json"):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "services": {
                            COMMUNICATIONS_WORKER_SERVICE: {
                                "environment": {
                                    "COMMUNICATIONS_WORKER_ENABLED": "false",
                                    "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE": "false",
                                }
                            }
                        }
                    }
                ),
                stderr="",
            )
        if args[:3] == ("ps", "--status", "running"):
            payload = "\n".join(
                json.dumps(
                    {
                        "Service": service,
                        "Labels": "com.docker.compose.oneoff=False",
                    }
                )
                for service in sorted(self.services)
            )
            return SimpleNamespace(
                returncode=0,
                stdout=payload + ("\n" if payload else ""),
                stderr="",
            )
        if args[:3] == ("ps", "--all", "--quiet"):
            service = args[-1]
            output = f"id-{service}\n" if service in self.services else ""
            return SimpleNamespace(returncode=0, stdout=output, stderr="")
        if args[:3] == ("exec", "-T", COMMUNICATIONS_WORKER_SERVICE):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[0] == "up":
            self.services.add(args[-1])
        elif args[0] in {"rm", "kill", "stop"}:
            self.services.discard(args[-1])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def docker(self, *args, **_kwargs):
        self.events.append(("docker", args))
        if args[:2] == ("ps", "--all"):
            output = (
                f"{self.container_id}\n"
                if COMMUNICATIONS_WORKER_SERVICE in self.services
                else ""
            )
            return SimpleNamespace(returncode=0, stdout=output, stderr="")
        if args[0] == "rm":
            self.services.discard(COMMUNICATIONS_WORKER_SERVICE)
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def _patch_runtime(monkeypatch, runtime: _Runtime, later_checks: list[str]) -> None:
    monkeypatch.setattr(patroni_role_agent, "_run_compose", runtime.compose)
    monkeypatch.setattr(patroni_role_agent, "_run_docker", runtime.docker)
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
    def systemd_units_match(*_args):
        later_checks.append("systemd")
        runtime.events.append(("later", ("systemd",)))
        return True

    monkeypatch.setattr(
        patroni_role_agent,
        "_systemd_units_match",
        systemd_units_match,
    )
    monkeypatch.setattr(
        patroni_role_agent,
        "_require_fresh_primary_or_fence",
        lambda *_args: None,
    )
    monkeypatch.setattr(patroni_role_agent, "_wait_ready", lambda _config: None)


@pytest.mark.parametrize("role", ["primary", "standby"])
def test_release_marker_fences_worker_and_suppresses_restarts_on_repeated_polls(
    tmp_path, monkeypatch, capsys, role
):
    config = _config(tmp_path)
    _prime_role(config, role)
    marker = tmp_path / COMMUNICATIONS_WORKER_RELEASE_FENCE_BASENAME
    marker.touch()
    runtime = _Runtime(worker_running=True)
    later_checks: list[str] = []
    _patch_runtime(monkeypatch, runtime, later_checks)

    assert patroni_role_agent.reconcile(config, role) is True

    remove_event = ("docker", ("rm", "--force", runtime.container_id))
    assert runtime.events.index(remove_event) < runtime.events.index(
        ("later", ("systemd",))
    )
    assert later_checks
    assert COMMUNICATIONS_WORKER_SERVICE not in runtime.services
    assert not any(
        event[0] == "compose"
        and event[1][0] == "up"
        and event[1][-1] == COMMUNICATIONS_WORKER_SERVICE
        for event in runtime.events
    )
    output = capsys.readouterr().out
    assert "communications_worker_release_fenced" in output
    assert "fence_communications_worker_release" in output
    assert marker.name not in output

    runtime.events.clear()
    later_checks.clear()
    assert patroni_role_agent.reconcile(config, role) is True
    assert COMMUNICATIONS_WORKER_SERVICE not in runtime.services
    assert not any(
        event[0] == "compose"
        and event[1][0] == "up"
        and event[1][-1] == COMMUNICATIONS_WORKER_SERVICE
        for event in runtime.events
    )
    assert marker.exists()


def test_broken_symlink_marker_is_honored_without_reading_target(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    _prime_role(config, "primary")
    marker = tmp_path / COMMUNICATIONS_WORKER_RELEASE_FENCE_BASENAME
    marker.symlink_to(tmp_path / "missing-release-owner")
    runtime = _Runtime(worker_running=True)
    _patch_runtime(monkeypatch, runtime, [])

    assert patroni_role_agent.reconcile(config, "primary") is True

    assert COMMUNICATIONS_WORKER_SERVICE not in runtime.services
    assert marker.is_symlink()


def test_absent_marker_keeps_normal_worker_requirement(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _prime_role(config, "primary")
    runtime = _Runtime(worker_running=False)
    _patch_runtime(monkeypatch, runtime, [])

    assert patroni_role_agent.reconcile(config, "primary") is True

    assert COMMUNICATIONS_WORKER_SERVICE in runtime.services
    assert any(
        event[0] == "compose"
        and event[1][0] == "up"
        and event[1][-1] == COMMUNICATIONS_WORKER_SERVICE
        for event in runtime.events
    )


def test_release_marker_inventory_failure_is_fail_closed_before_slow_checks(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    _prime_role(config, "primary")
    (tmp_path / COMMUNICATIONS_WORKER_RELEASE_FENCE_BASENAME).touch()
    runtime = _Runtime(worker_running=True)
    later_checks: list[str] = []
    _patch_runtime(monkeypatch, runtime, later_checks)
    monkeypatch.setattr(
        patroni_role_agent,
        "_run_docker",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="docker unavailable",
        ),
    )

    with pytest.raises(RuntimeError, match="docker unavailable"):
        patroni_role_agent.reconcile(config, "primary")

    assert later_checks == []
    assert not runtime.events
