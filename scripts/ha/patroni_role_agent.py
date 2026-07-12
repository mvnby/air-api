#!/usr/bin/env python3
"""Reconcile API, scheduler, and bot runtime state with the local Patroni role."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


PRIMARY_ROLES = {"leader", "master", "primary"}


@dataclass(frozen=True)
class AgentConfig:
    project_dir: Path
    compose_file: str
    patroni_url: str
    ready_url: str
    app_role_env: Path
    bot_role_env: Path
    state_file: Path
    deploy_lock: Path
    active_slot_file: Path
    app_service: str
    primary_systemd_units: tuple[str, ...]
    poll_seconds: int
    promotion_delay_seconds: int
    ready_attempts: int


def _integer(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def load_config() -> AgentConfig:
    project_dir = Path(os.getenv("HA_PROJECT_DIR", "/opt/air-api")).resolve()
    compose_file = os.getenv("HA_COMPOSE_FILE", "docker-compose.prod.yml").strip()
    return AgentConfig(
        project_dir=project_dir,
        compose_file=compose_file,
        patroni_url=os.getenv("HA_PATRONI_URL", "http://127.0.0.1:8008/patroni").rstrip("/"),
        ready_url=os.getenv("HA_READY_URL", "http://127.0.0.1:18080/api/ready"),
        app_role_env=project_dir / ".ha-app-role.env",
        bot_role_env=project_dir / ".ha-bot-role.env",
        state_file=project_dir / ".ha-runtime-role",
        deploy_lock=project_dir / ".deploy.lock",
        active_slot_file=project_dir / ".active-api-slot",
        app_service=os.getenv("HA_APP_SERVICE", "").strip(),
        primary_systemd_units=tuple(os.getenv("HA_PRIMARY_SYSTEMD_UNITS", "").split()),
        poll_seconds=_integer("HA_ROLE_POLL_SECONDS", 3),
        promotion_delay_seconds=_integer("HA_PROMOTION_DELAY_SECONDS", 8, minimum=0),
        ready_attempts=_integer("HA_READY_ATTEMPTS", 30),
    )


def fetch_patroni_role(url: str, *, timeout: float = 3.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("state") != "running":
        return "standby"
    role = str(payload.get("role") or "").strip().lower()
    return "primary" if role in PRIMARY_ROLES else "standby"


def app_service(config: AgentConfig) -> str:
    if config.app_service:
        return config.app_service
    try:
        slot = config.active_slot_file.read_text(encoding="utf-8").strip().lower()
    except FileNotFoundError:
        slot = ""
    if slot in {"blue", "green"}:
        return f"app-{slot}"
    return "app"


def role_env(role: str, *, bot_process: bool) -> str:
    primary = role == "primary"
    values = {
        "APP_ROLE": role,
        "API_READY_ENABLED": "false" if bot_process else str(primary).lower(),
        "BOT_ENABLED": str(primary and bot_process).lower(),
        "DB_BOOTSTRAP_ENABLED": "false",
        "SCHEDULER_ENABLED": str(primary and not bot_process).lower(),
    }
    if not primary:
        values.update(
            {
                "MAIL_IMAP_AUTO_IMPORT_ENABLED": "false",
                "MAIL_IMAP_LEAD_AUTO_IMPORT_ENABLED": "false",
                "CLOUDFLARE_PURGE_ENABLED": "false",
                "CLOUDFLARE_PURGE_DRY_RUN": "true",
            }
        )
    return "".join(f"{name}={value}\n" for name, value in values.items())


def _atomic_write(path: Path, content: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _run_compose(config: AgentConfig, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "-f", config.compose_file, *args]
    return subprocess.run(
        command,
        cwd=config.project_dir,
        check=check,
        text=True,
        capture_output=True,
    )


def _running_services(config: AgentConfig) -> set[str]:
    result = _run_compose(config, "ps", "--status", "running", "--services", check=False)
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "docker compose ps failed").strip()
        raise RuntimeError(error)
    return set(result.stdout.splitlines())


def _start_service(config: AgentConfig, service: str, *, recreate: bool) -> None:
    args = ["up", "-d", "--no-deps"]
    if recreate:
        args.append("--force-recreate")
    args.append(service)
    _run_compose(config, *args)


def _systemd_units_match(config: AgentConfig, role: str) -> bool:
    expected_active = role == "primary"
    for unit in config.primary_systemd_units:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            check=False,
            capture_output=True,
            text=True,
        )
        if (result.returncode == 0) != expected_active:
            return False
    return True


def _reconcile_primary_systemd_units(config: AgentConfig, role: str) -> None:
    action = "start" if role == "primary" else "stop"
    for unit in config.primary_systemd_units:
        result = subprocess.run(
            ["systemctl", action, unit],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout).strip().replace("\n", " ")
            print(
                f"patroni_role_agent_status=warning systemd_unit={unit} "
                f"action={action} error={error or result.returncode}",
                flush=True,
            )


def _wait_ready(config: AgentConfig) -> None:
    for _ in range(config.ready_attempts):
        try:
            with urllib.request.urlopen(config.ready_url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if (
                response.status == 200
                and payload.get("api") == "ready"
                and payload.get("database_writable") is True
            ):
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise RuntimeError(f"primary API did not become ready: {config.ready_url}")


def reconcile(config: AgentConfig, role: str) -> bool:
    desired_app = role_env(role, bot_process=False)
    desired_bot = role_env(role, bot_process=True)
    current_state = config.state_file.read_text(encoding="utf-8").strip() if config.state_file.exists() else ""
    app_matches = config.app_role_env.exists() and config.app_role_env.read_text(encoding="utf-8") == desired_app
    bot_matches = config.bot_role_env.exists() and config.bot_role_env.read_text(encoding="utf-8") == desired_bot
    service = app_service(config)
    running = _running_services(config)
    role_changed = current_state != role
    app_env_changed = not app_matches
    bot_env_changed = not bot_matches
    app_running = service in running
    bot_running = "bot" in running
    bot_expected = role == "primary"
    systemd_matches = _systemd_units_match(config, role)

    reasons: list[str] = []
    if role_changed:
        reasons.append("role_state")
    if app_env_changed:
        reasons.append("app_env")
    if bot_env_changed:
        reasons.append("bot_env")
    if not app_running:
        reasons.append("app_not_running")
    if bot_expected and not bot_running:
        reasons.append("bot_not_running")
    if not bot_expected and bot_running:
        reasons.append("bot_running_on_standby")
    if not systemd_matches:
        reasons.append("systemd_units")

    needs_runtime_reconcile = (
        role_changed
        or app_env_changed
        or bot_env_changed
        or not app_running
        or bot_running != bot_expected
    )
    if not needs_runtime_reconcile:
        if not systemd_matches:
            _reconcile_primary_systemd_units(config, role)
        return False

    config.deploy_lock.parent.mkdir(parents=True, exist_ok=True)
    with config.deploy_lock.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("patroni_role_agent_status=deferred reason=deployment_lock_busy", flush=True)
            return False

        if role == "primary" and role_changed and config.promotion_delay_seconds:
            time.sleep(config.promotion_delay_seconds)
            if fetch_patroni_role(config.patroni_url) != "primary":
                print("patroni_role_agent_status=deferred reason=primary_role_not_stable", flush=True)
                return False

        actions: list[str] = []
        if app_env_changed:
            _atomic_write(config.app_role_env, desired_app)
            actions.append("write_app_env")
        if bot_env_changed:
            _atomic_write(config.bot_role_env, desired_bot)
            actions.append("write_bot_env")

        app_needs_start = app_env_changed or not app_running
        if role == "standby":
            if not systemd_matches:
                _reconcile_primary_systemd_units(config, role)
                actions.append("stop_primary_units")
            if bot_running:
                _run_compose(config, "stop", "bot", check=False)
                actions.append("stop_bot")
            if app_needs_start:
                _start_service(config, service, recreate=app_env_changed)
                actions.append("recreate_app" if app_env_changed else "start_app")
        else:
            if app_needs_start:
                _start_service(config, service, recreate=app_env_changed)
                actions.append("recreate_app" if app_env_changed else "start_app")
            bot_needs_start = bot_env_changed or not bot_running
            if app_needs_start or bot_needs_start:
                _wait_ready(config)
                actions.append("wait_ready")
            if bot_needs_start:
                _start_service(config, "bot", recreate=bot_env_changed)
                actions.append("recreate_bot" if bot_env_changed else "start_bot")
            if not systemd_matches:
                _reconcile_primary_systemd_units(config, role)
                actions.append("start_primary_units")

        if role_changed:
            _atomic_write(config.state_file, f"{role}\n")
            actions.append("write_role_state")
        print(
            f"patroni_role_agent_status=reconciled role={role} app_service={service} "
            f"reasons={','.join(reasons)} actions={','.join(actions)}",
            flush=True,
        )
        return True


def run(config: AgentConfig, *, once: bool) -> int:
    while True:
        try:
            role = fetch_patroni_role(config.patroni_url)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            role = "standby"
            print(f"patroni_role_agent_status=warning patroni_unavailable={exc}", flush=True)
        try:
            reconcile(config, role)
        except Exception as exc:
            print(f"patroni_role_agent_status=failed role={role} error={exc}", flush=True)
            if once:
                return 1
        if once:
            return 0
        time.sleep(config.poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        config = load_config()
    except ValueError as exc:
        print(f"patroni_role_agent_status=failed error={exc}")
        return 2
    return run(config, once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
