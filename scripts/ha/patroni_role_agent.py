#!/usr/bin/env python3
"""Reconcile API and scheduler runtime state with the local Patroni role.

The Telegram polling runtime is an external service. The legacy Compose service
is kept stopped on both database roles to prevent two consumers from polling the
same Telegram token during and after extraction.
"""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    from scripts.ha.patroni_local_identity import (
        atomic_write as _atomic_write,
        fetch_patroni_role,
        integer_env as _integer,
        read_maintenance_transaction_id,
        reconcile_primary_systemd_units as _reconcile_systemd_units,
        render_role_env as role_env,
        resolve_app_service as app_service,
        systemd_units_match as _identity_systemd_units_match,
        wait_primary_ready as _wait_ready,
    )
except ModuleNotFoundError:
    from patroni_local_identity import (
        atomic_write as _atomic_write,
        fetch_patroni_role,
        integer_env as _integer,
        read_maintenance_transaction_id,
        reconcile_primary_systemd_units as _reconcile_systemd_units,
        render_role_env as role_env,
        resolve_app_service as app_service,
        systemd_units_match as _identity_systemd_units_match,
        wait_primary_ready as _wait_ready,
    )


OPERATION_GUARD_PATH = Path("/usr/local/sbin/mvn_postgres_pitr_operation_guard.py")
COMMAND_TIMEOUT_SECONDS = 60
EXPECTED_LOCAL_PATRONI_URL = "http://127.0.0.1:8008/patroni"
EXPECTED_PATRONI_SCOPE = "mvn-postgres"
DEFAULT_MAX_DCS_AGE_SECONDS = 20
MAX_CONFIGURED_DCS_AGE_SECONDS = 20
PRODUCTION_NODE_NAMES = {Path("/opt/air-api"): "mvn-api", Path("/opt/mvn-reserve"): "zakup"}
REVIEWED_PRIMARY_SYSTEMD_UNITS = (
    "mvn-postgres-wal-upload.timer",
    "mvn-postgres-basebackup.timer",
)
APP_SERVICE_NAMES = ("app", "app-blue", "app-green")
CONTAINER_PROXY_SERVICE = "api-proxy"


@dataclass(frozen=True)
class AgentConfig:
    project_dir: Path
    compose_file: str
    patroni_url: str
    patroni_scope: str
    patroni_name: str
    max_dcs_age_seconds: int
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


def load_config() -> AgentConfig:
    project_dir = Path(os.getenv("HA_PROJECT_DIR", "/opt/air-api")).resolve()
    compose_file = os.getenv("HA_COMPOSE_FILE", "docker-compose.prod.yml").strip()
    patroni_url = os.getenv("HA_PATRONI_URL", EXPECTED_LOCAL_PATRONI_URL).rstrip("/")
    if patroni_url != EXPECTED_LOCAL_PATRONI_URL:
        raise ValueError(f"HA_PATRONI_URL must be {EXPECTED_LOCAL_PATRONI_URL}")
    patroni_scope = os.getenv("HA_PATRONI_SCOPE", EXPECTED_PATRONI_SCOPE).strip()
    if patroni_scope != EXPECTED_PATRONI_SCOPE:
        raise ValueError(f"HA_PATRONI_SCOPE must be {EXPECTED_PATRONI_SCOPE}")
    inferred_patroni_name = PRODUCTION_NODE_NAMES.get(project_dir, "")
    patroni_name = os.getenv("HA_PATRONI_NAME", inferred_patroni_name).strip()
    if not inferred_patroni_name:
        raise ValueError(f"HA_PROJECT_DIR is not a reviewed Patroni node path: {project_dir}")
    if patroni_name != inferred_patroni_name:
        raise ValueError(
            f"HA_PATRONI_NAME must be {inferred_patroni_name} for {project_dir}"
        )
    max_dcs_age_seconds = _integer(
        "HA_PATRONI_MAX_DCS_AGE_SECONDS", DEFAULT_MAX_DCS_AGE_SECONDS
    )
    if max_dcs_age_seconds > MAX_CONFIGURED_DCS_AGE_SECONDS:
        raise ValueError(
            "HA_PATRONI_MAX_DCS_AGE_SECONDS must not exceed the reviewed 20s bound"
        )
    raw_units = os.getenv(
        "HA_PRIMARY_SYSTEMD_UNITS", " ".join(REVIEWED_PRIMARY_SYSTEMD_UNITS)
    )
    primary_systemd_units = tuple(raw_units.split())
    if primary_systemd_units != REVIEWED_PRIMARY_SYSTEMD_UNITS:
        raise ValueError(
            "HA_PRIMARY_SYSTEMD_UNITS must contain the exact reviewed PITR timers"
        )
    return AgentConfig(
        project_dir=project_dir,
        compose_file=compose_file,
        patroni_url=patroni_url,
        patroni_scope=patroni_scope,
        patroni_name=patroni_name,
        max_dcs_age_seconds=max_dcs_age_seconds,
        ready_url=os.getenv("HA_READY_URL", "http://127.0.0.1:18080/api/ready"),
        app_role_env=project_dir / ".ha-app-role.env",
        bot_role_env=project_dir / ".ha-bot-role.env",
        state_file=project_dir / ".ha-runtime-role",
        deploy_lock=project_dir / ".deploy.lock",
        active_slot_file=project_dir / ".active-api-slot",
        app_service=os.getenv("HA_APP_SERVICE", "").strip(),
        primary_systemd_units=primary_systemd_units,
        poll_seconds=_integer("HA_ROLE_POLL_SECONDS", 3),
        promotion_delay_seconds=_integer("HA_PROMOTION_DELAY_SECONDS", 8, minimum=0),
        ready_attempts=_integer("HA_READY_ATTEMPTS", 30),
    )


def _fetch_configured_patroni_role(config: AgentConfig) -> str:
    return fetch_patroni_role(
        config.patroni_url,
        expected_name=config.patroni_name,
        expected_scope=config.patroni_scope,
        max_dcs_age_seconds=config.max_dcs_age_seconds,
    )


def _run_compose(
    config: AgentConfig,
    *args: str,
    check: bool = True,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "--profile", "bluegreen", "-f", config.compose_file, *args]
    return subprocess.run(
        command,
        cwd=config.project_dir,
        check=check,
        text=True,
        capture_output=True,
        timeout=timeout,
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


def _refresh_container_proxy_dns(
    config: AgentConfig,
    *,
    running_services: set[str],
) -> bool:
    """Refresh nginx's startup-time Docker DNS after an app container changes."""

    if CONTAINER_PROXY_SERVICE not in running_services:
        return False
    _run_compose(config, "restart", CONTAINER_PROXY_SERVICE)
    return True


def _stop_service_verified(config: AgentConfig, service: str) -> None:
    error = ""
    try:
        removed = _run_compose(
            config, "rm", "--stop", "--force", service, check=False, timeout=20
        )
        error = (removed.stderr or removed.stdout).strip()
    except subprocess.TimeoutExpired:
        error = "container removal timed out"
    try:
        remaining = _run_compose(
            config, "ps", "--all", "--quiet", service, check=False, timeout=10
        )
    except subprocess.TimeoutExpired:
        remaining = subprocess.CompletedProcess([], 1, "", "container inventory timed out")
    if remaining.returncode == 0 and not remaining.stdout.strip():
        return
    try:
        _run_compose(
            config, "kill", "--signal", "SIGKILL", service, check=False, timeout=10
        )
    except subprocess.TimeoutExpired:
        pass
    try:
        forced = _run_compose(
            config, "rm", "--force", service, check=False, timeout=20
        )
        error = (forced.stderr or forced.stdout or error).strip()
    except subprocess.TimeoutExpired:
        error = "forced container removal timed out"
    final = _run_compose(
        config, "ps", "--all", "--quiet", service, check=False, timeout=10
    )
    if final.returncode != 0 or final.stdout.strip():
        raise RuntimeError(
            f"could not fence Compose service {service}: {error or 'container remains'}"
        )


def _cancel_pitr_operations(config: AgentConfig) -> list[str]:
    if not Path("/run/mvn-postgres-pitr-operations").exists():
        return []
    try:
        from scripts.ha.pitr_operation_guard import cancel_project_operations
    except ModuleNotFoundError:
        specification = importlib.util.spec_from_file_location(
            "mvn_postgres_pitr_operation_guard",
            OPERATION_GUARD_PATH,
        )
        if specification is None or specification.loader is None:
            if Path("/run/mvn-postgres-pitr-operations").exists():
                raise RuntimeError("PITR operation guard is unavailable")
            return []
        module = importlib.util.module_from_spec(specification)
        sys.modules[specification.name] = module
        specification.loader.exec_module(module)
        cancel_project_operations = module.cancel_project_operations
    return cancel_project_operations(str(config.project_dir))


def _systemd_units_match(config: AgentConfig, role: str) -> bool:
    return _identity_systemd_units_match(config, role)


def _reconcile_primary_systemd_units(
    config: AgentConfig,
    role: str,
    *,
    primary_guard: Callable[[str], None] | None = None,
) -> None:
    _reconcile_systemd_units(
        config,
        role,
        primary_guard=primary_guard,
        state_probe=_systemd_units_match,
    )


def _fence_lost_primary(config: AgentConfig) -> None:
    """Best-effort immediate fence that does not wait for the deploy lock."""

    failures: list[str] = []
    fencing_state_persisted = False
    try:
        # This is a durable retry marker, not a cosmetic status. A crash or any
        # failed postcondition must leave a value different from ``standby`` so
        # the next standby poll repeats the exact-name fence.
        _atomic_write(config.state_file, "fencing\n")
        fencing_state_persisted = True
    except Exception as exc:
        failures.append(f"state_fencing:{exc}")
    standby_app = role_env("standby", bot_process=False)
    standby_bot = role_env("standby", bot_process=True)
    if fencing_state_persisted:
        for label, path, content in (
            ("app_env", config.app_role_env, standby_app),
            ("bot_env", config.bot_role_env, standby_bot),
        ):
            try:
                _atomic_write(path, content)
            except Exception as exc:
                failures.append(f"{label}:{exc}")

    # Do not trust an earlier Compose inventory here. A deployment may have
    # started a side-effect owner between the failed identity check and fence.
    for service in ("bot", *APP_SERVICE_NAMES):
        try:
            _stop_service_verified(config, service)
        except Exception as exc:
            failures.append(f"{service}:{exc}")

    try:
        _cancel_pitr_operations(config)
    except Exception as exc:
        failures.append(f"pitr:{exc}")
    try:
        _reconcile_primary_systemd_units(config, "standby")
    except Exception as exc:
        failures.append(f"systemd:{exc}")
    if failures:
        raise RuntimeError("standby fence incomplete: " + "; ".join(failures))


def _maintenance_transaction_or_fence(config: AgentConfig) -> str | None:
    try:
        return read_maintenance_transaction_id()
    except Exception as marker_error:
        fence_error = ""
        try:
            _fence_lost_primary(config)
        except Exception as exc:
            fence_error = f"; fence_error={exc}"
        raise RuntimeError(
            f"unsafe PITR maintenance marker: {marker_error}{fence_error}"
        ) from marker_error


def _require_fresh_primary_or_fence(config: AgentConfig, boundary: str) -> None:
    maintenance_transaction = _maintenance_transaction_or_fence(config)
    if maintenance_transaction is not None and not _systemd_units_match(
        config, "standby"
    ):
        _reconcile_primary_systemd_units(config, "standby")
    probe_error = ""
    try:
        live_role = _fetch_configured_patroni_role(config)
    except Exception as exc:
        live_role = "standby"
        probe_error = f"{type(exc).__name__}: {exc}"
    if live_role == "primary":
        return

    fence_error = ""
    try:
        _fence_lost_primary(config)
    except Exception as exc:
        fence_error = f"; fence_error={exc}"
    detail = probe_error or f"live_role={live_role}"
    print(
        "patroni_role_agent_status=fenced "
        f"reason=primary_identity_lost boundary={boundary} detail={detail}{fence_error}",
        flush=True,
    )
    raise RuntimeError(
        f"fresh Patroni primary proof failed at {boundary}: {detail}{fence_error}"
    )


def _guard_pitr_activation(config: AgentConfig, unit: str) -> None:
    _require_fresh_primary_or_fence(config, f"systemd_activation:{unit}")
    if _maintenance_transaction_or_fence(config) is not None:
        if not _systemd_units_match(config, "standby"):
            _reconcile_primary_systemd_units(config, "standby")
        raise RuntimeError(
            f"PITR maintenance marker appeared before activation of {unit}"
        )


def reconcile(config: AgentConfig, role: str) -> bool:
    maintenance_transaction = _maintenance_transaction_or_fence(config)
    pitr_role = "standby" if maintenance_transaction is not None else role
    desired_app = role_env(role, bot_process=False)
    desired_bot = role_env(role, bot_process=True, bot_enabled=False)
    current_state = (
        config.state_file.read_text(encoding="utf-8").strip()
        if config.state_file.exists()
        else ""
    )
    app_matches = (
        config.app_role_env.exists()
        and config.app_role_env.read_text(encoding="utf-8") == desired_app
    )
    bot_matches = (
        config.bot_role_env.exists()
        and config.bot_role_env.read_text(encoding="utf-8") == desired_bot
    )
    role_changed = current_state != role
    app_env_changed = not app_matches
    bot_env_changed = not bot_matches
    fast_fenced = False
    if role == "standby" and (role_changed or app_env_changed or bot_env_changed):
        # Losing primary ownership is an emergency path: fence by exact service
        # name before trusting Docker inventory, which can itself fail or hang.
        _fence_lost_primary(config)
        fast_fenced = True
    service = app_service(config)
    running = _running_services(config)
    app_running = service in running
    bot_running = "bot" in running
    bot_expected = False
    # On demotion, Docker singleton fencing must happen before any fallible or
    # slow systemd D-Bus inspection.  A ten-second query timeout is already too
    # long to leave old-primary workers live beside a new primary.
    systemd_matches = (
        False
        if role == "standby"
        else _systemd_units_match(config, pitr_role)
    )

    reasons: list[str] = []
    if role_changed:
        reasons.append("role_state")
    if app_env_changed:
        reasons.append("app_env")
    if bot_env_changed:
        reasons.append("bot_env")
    if not app_running:
        reasons.append("app_not_running")
    if bot_running:
        reasons.append("legacy_bot_running")
    if not systemd_matches:
        reasons.append("systemd_units")
    if maintenance_transaction is not None:
        reasons.append("pitr_maintenance")

    actions: list[str] = []
    if fast_fenced:
        actions.append("demotion_fast_fence")
    if bot_running:
        # The polling process is owned by mvn-telegram-bot now. Fence the old
        # Compose service before the deployment lock so a concurrent API
        # release cannot prolong duplicate Telegram polling.
        _stop_service_verified(config, "bot")
        bot_running = False
        actions.append("stop_legacy_bot_prelock")
    if role == "standby":
        # Demotion fencing has priority over deploys and long-running PITR jobs.
        # Persist the fenced environment first, then stop every local side-effect
        # owner before attempting the shared deploy lock.
        if app_env_changed:
            _atomic_write(config.app_role_env, desired_app)
            actions.append("write_app_env_prelock")
        if bot_env_changed:
            _atomic_write(config.bot_role_env, desired_bot)
            actions.append("write_bot_env_prelock")
        running_apps = [name for name in APP_SERVICE_NAMES if name in running]
        if (
            fast_fenced
            or role_changed
            or app_env_changed
            or any(name != service for name in running_apps)
        ):
            for running_app in running_apps:
                _stop_service_verified(config, running_app)
            app_running = False
            if running_apps:
                actions.append("stop_apps_prelock")
        cancelled_operations = _cancel_pitr_operations(config)
        if cancelled_operations:
            actions.append("cancel_pitr_prelock")
        systemd_matches = _systemd_units_match(config, role)
        if not systemd_matches:
            _reconcile_primary_systemd_units(config, role)
            systemd_matches = _systemd_units_match(config, role)
            if not systemd_matches:
                raise RuntimeError("primary-only systemd units remained active after stop")
            actions.append("stop_primary_units_prelock")
    elif maintenance_transaction is not None and not systemd_matches:
        _reconcile_primary_systemd_units(config, "standby")
        systemd_matches = _systemd_units_match(config, "standby")
        if not systemd_matches:
            raise RuntimeError("PITR units remained active during maintenance")
        actions.append("stop_pitr_units_for_maintenance_prelock")

    needs_runtime_reconcile = (
        role_changed
        or app_env_changed
        or bot_env_changed
        or not app_running
        or bot_running != bot_expected
    )
    if not needs_runtime_reconcile and systemd_matches:
        if actions:
            print(
                f"patroni_role_agent_status=reconciled role={role} "
                f"app_service={service} reasons={','.join(reasons)} "
                f"actions={','.join(actions)}",
                flush=True,
            )
            return True
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
            _require_fresh_primary_or_fence(config, "promotion_delay")

        if app_env_changed:
            if role != "standby":
                _require_fresh_primary_or_fence(config, "primary_app_env")
                _atomic_write(config.app_role_env, desired_app)
                actions.append("write_app_env")
        if bot_env_changed:
            if role != "standby":
                _atomic_write(config.bot_role_env, desired_bot)
                actions.append("write_bot_env")

        # Re-read after acquiring the lock: a concurrent deploy may have changed
        # the concrete containers while fail-safe pre-lock fencing was running.
        running = _running_services(config)
        app_running = service in running
        bot_running = "bot" in running

        if bot_running:
            _stop_service_verified(config, "bot")
            bot_running = False
            actions.append("stop_legacy_bot")

        app_needs_start = fast_fenced or app_env_changed or role_changed or not app_running
        if role == "standby":
            if not systemd_matches:
                _reconcile_primary_systemd_units(config, role)
                actions.append("stop_primary_units")
            for running_app in APP_SERVICE_NAMES:
                if running_app != service and running_app in running:
                    _stop_service_verified(config, running_app)
                    actions.append("stop_extra_app")
            if app_needs_start:
                recreate_app = fast_fenced or app_env_changed or role_changed
                _start_service(config, service, recreate=recreate_app)
                actions.append(
                    "recreate_app" if recreate_app else "start_app"
                )
                if _refresh_container_proxy_dns(
                    config,
                    running_services=running,
                ):
                    actions.append("refresh_container_proxy_dns")
            final_running = _running_services(config)
            if (
                service not in final_running
                or "bot" in final_running
                or any(
                    name in final_running for name in APP_SERVICE_NAMES if name != service
                )
            ):
                raise RuntimeError("standby runtime fencing postcondition failed")
        else:
            if app_needs_start:
                _require_fresh_primary_or_fence(config, "app_activation")
                _start_service(config, service, recreate=app_env_changed)
                actions.append("recreate_app" if app_env_changed else "start_app")
                if _refresh_container_proxy_dns(
                    config,
                    running_services=running,
                ):
                    actions.append("refresh_container_proxy_dns")
            if app_needs_start:
                _wait_ready(config)
                actions.append("wait_ready")
            if not systemd_matches:
                if maintenance_transaction is not None:
                    _reconcile_primary_systemd_units(config, "standby")
                    actions.append("stop_pitr_units_for_maintenance")
                else:
                    _reconcile_primary_systemd_units(
                        config,
                        role,
                        primary_guard=lambda unit: _guard_pitr_activation(config, unit),
                    )
                    actions.append("start_primary_units")
            live_maintenance = _maintenance_transaction_or_fence(config)
            if live_maintenance is not None and not _systemd_units_match(
                config, "standby"
            ):
                _reconcile_primary_systemd_units(config, "standby")
                actions.append("stop_pitr_units_for_new_maintenance")
            _require_fresh_primary_or_fence(config, "primary_postcondition")
            final_maintenance = _maintenance_transaction_or_fence(config)
            if final_maintenance is not None and not _systemd_units_match(
                config, "standby"
            ):
                _reconcile_primary_systemd_units(config, "standby")
                actions.append("stop_pitr_units_for_final_maintenance")
            final_running = _running_services(config)
            if service not in final_running or "bot" in final_running:
                raise RuntimeError("primary runtime activation postcondition failed")
            expected_pitr_role = (
                "standby"
                if any(
                    value is not None
                    for value in (
                        maintenance_transaction,
                        live_maintenance,
                        final_maintenance,
                    )
                )
                else "primary"
            )
            if not _systemd_units_match(config, expected_pitr_role):
                raise RuntimeError("primary PITR systemd postcondition failed")

        if role_changed or fast_fenced:
            if role == "primary":
                _require_fresh_primary_or_fence(config, "primary_state")
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
            role = _fetch_configured_patroni_role(config)
        except Exception as exc:
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
