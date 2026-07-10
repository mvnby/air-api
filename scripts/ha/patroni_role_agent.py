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


def _runtime_matches(config: AgentConfig, role: str, service: str) -> bool:
    result = _run_compose(config, "ps", "--status", "running", "--services", check=False)
    if result.returncode != 0:
        return False
    running = set(result.stdout.splitlines())
    if service not in running:
        return False
    return ("bot" in running) == (role == "primary")


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
    if (
        current_state == role
        and app_matches
        and bot_matches
        and _runtime_matches(config, role, service)
    ):
        return False

    config.deploy_lock.parent.mkdir(parents=True, exist_ok=True)
    with config.deploy_lock.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("patroni_role_agent_status=deferred reason=deployment_lock_busy", flush=True)
            return False

        if role == "primary" and config.promotion_delay_seconds:
            time.sleep(config.promotion_delay_seconds)
            if fetch_patroni_role(config.patroni_url) != "primary":
                print("patroni_role_agent_status=deferred reason=primary_role_not_stable", flush=True)
                return False

        _atomic_write(config.app_role_env, desired_app)
        _atomic_write(config.bot_role_env, desired_bot)
        if role == "standby":
            _run_compose(config, "stop", "bot", check=False)
            _run_compose(config, "up", "-d", "--no-deps", "--force-recreate", service)
        else:
            _run_compose(config, "up", "-d", "--no-deps", "--force-recreate", service)
            _wait_ready(config)
            _run_compose(config, "up", "-d", "--no-deps", "--force-recreate", "bot")

        _atomic_write(config.state_file, f"{role}\n")
        print(f"patroni_role_agent_status=reconciled role={role} app_service={service}", flush=True)
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
