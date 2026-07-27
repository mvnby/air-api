#!/usr/bin/env python3
"""Reconcile API and scheduler runtime state with the local Patroni role.

The Telegram polling runtime is an external service. The legacy Compose service
is kept stopped on both database roles to prevent two consumers from polling the
same Telegram token during and after extraction.
"""

from __future__ import annotations

import argparse
import fcntl
import time
from typing import Callable

try:
    from scripts.ha.patroni_compose_runtime import (
        ComposeRuntime,
        cancel_pitr_operations,
        run_compose,
        run_docker,
        wait_scheduler_running,
    )
    from scripts.ha.patroni_local_identity import (
        COMMUNICATIONS_WORKER_SERVICE,
        atomic_write as _atomic_write,
        communications_worker_contract_state as _communications_worker_contract_state,
        read_maintenance_transaction_id,
        reconcile_primary_systemd_units as _reconcile_systemd_units,
        render_role_env as role_env,
        resolve_app_service as app_service,
        systemd_units_match as _identity_systemd_units_match,
        wait_primary_ready as _wait_ready,
    )
    from scripts.ha.patroni_role_agent_config import (
        APP_SERVICE_NAMES,
        AgentConfig,
        fetch_configured_patroni_role as _fetch_configured_patroni_role,
        load_config,
    )
except ModuleNotFoundError:
    from patroni_compose_runtime import (
        ComposeRuntime,
        cancel_pitr_operations,
        run_compose,
        run_docker,
        wait_scheduler_running,
    )
    from patroni_local_identity import (
        COMMUNICATIONS_WORKER_SERVICE,
        atomic_write as _atomic_write,
        communications_worker_contract_state as _communications_worker_contract_state,
        read_maintenance_transaction_id,
        reconcile_primary_systemd_units as _reconcile_systemd_units,
        render_role_env as role_env,
        resolve_app_service as app_service,
        systemd_units_match as _identity_systemd_units_match,
        wait_primary_ready as _wait_ready,
    )
    from patroni_role_agent_config import (
        APP_SERVICE_NAMES,
        AgentConfig,
        fetch_configured_patroni_role as _fetch_configured_patroni_role,
        load_config,
    )


_run_compose = run_compose
_run_docker = run_docker
_wait_scheduler_running = wait_scheduler_running
_cancel_pitr_operations = cancel_pitr_operations


def _compose_runtime(config: AgentConfig) -> ComposeRuntime:
    return ComposeRuntime(
        config,
        compose_runner=_run_compose,
        docker_runner=_run_docker,
        atomic_writer=_atomic_write,
    )


def _running_services(config: AgentConfig) -> set[str]:
    return _compose_runtime(config).running_services()


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

    compose = _compose_runtime(config)
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

    try:
        # This inventory bypasses rendered Compose entirely. During the first
        # modular rollout the new service may be absent from the installed
        # Compose file while an old-primary container still exists.
        compose.fence_labeled_service_containers(COMMUNICATIONS_WORKER_SERVICE)
    except Exception as exc:
        failures.append(f"{COMMUNICATIONS_WORKER_SERVICE}:{exc}")

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
            compose.stop_service_verified(service)
        except Exception as exc:
            failures.append(f"{service}:{exc}")

    try:
        _cancel_pitr_operations(config)
    except Exception as exc:
        failures.append(f"pitr:{exc}")
    try:
        # Close the race with a concurrent candidate deployment immediately
        # before touching primary-only systemd ownership.
        compose.fence_labeled_service_containers(COMMUNICATIONS_WORKER_SERVICE)
    except Exception as exc:
        failures.append(f"{COMMUNICATIONS_WORKER_SERVICE}_postcondition:{exc}")
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


def reconcile(config: AgentConfig, role: str) -> bool | None:
    compose = _compose_runtime(config)
    release_fenced = compose.enforce_worker_release_fence(COMMUNICATIONS_WORKER_SERVICE)
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
        # Demotion fast-fences exact side-effect owners before fallible inventory.
        _fence_lost_primary(config)
        fast_fenced = True
    service = app_service(config)
    running = compose.running_services()
    release_fenced = compose.enforce_worker_release_fence(
        COMMUNICATIONS_WORKER_SERVICE, latched=release_fenced
    )
    worker_state = _communications_worker_contract_state(
        config,
        role,
        compose=compose,
        running_services=running,
        release_fenced=release_fenced,
    )
    worker_defined = worker_state.defined
    worker_running = worker_state.running
    worker_role_matches = worker_state.role_matches
    worker_role_drift = worker_state.unsafe_mismatch
    worker_profile_drift = not worker_state.canonical_profile_matches
    if not worker_running:
        running.discard(COMMUNICATIONS_WORKER_SERVICE)
    if role == "standby" and worker_role_drift:
        # A living worker with the old primary role is equivalent to a lost
        # primary identity. Fence every local side-effect owner before the
        # later systemd probes or deploy-lock acquisition.
        _fence_lost_primary(config)
        fast_fenced = True
        running.difference_update(
            {"bot", COMMUNICATIONS_WORKER_SERVICE, *APP_SERVICE_NAMES}
        )
        worker_running = False
    app_running = service in running
    extra_running_apps = sorted(
        name for name in APP_SERVICE_NAMES if name != service and name in running
    )
    proxy_upstream_drift = not compose.container_proxy_upstream_matches(
        service,
        running_services=running,
    )
    bot_running = "bot" in running
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
    if role == "primary" and extra_running_apps:
        reasons.append("extra_app_running")
    if role == "primary" and proxy_upstream_drift:
        reasons.append("proxy_upstream_drift")
    if bot_running:
        reasons.append("legacy_bot_running")
    if worker_defined and not worker_running:
        reasons.append("communications_worker_not_running")
    if worker_role_drift:
        reasons.append("communications_worker_role_drift")
    if worker_profile_drift:
        reasons.append("communications_worker_profile_drift")
    if not systemd_matches:
        reasons.append("systemd_units")
    if maintenance_transaction is not None:
        reasons.append("pitr_maintenance")
    if release_fenced:
        reasons.append("communications_worker_release_fenced")

    actions: list[str] = []
    if release_fenced:
        actions.append("fence_communications_worker_release")
    if fast_fenced:
        actions.append("demotion_fast_fence")
    if bot_running:
        # The polling process is owned by mvn-telegram-bot now. Fence the old
        # Compose service before the deployment lock so a concurrent API
        # release cannot prolong duplicate Telegram polling.
        compose.stop_service_verified("bot")
        bot_running = False
        actions.append("stop_legacy_bot_prelock")
    if role == "standby":
        # Persist and fence standby ownership before waiting for the deploy lock.
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
                compose.stop_service_verified(running_app)
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
        or bot_running
        or (
            worker_defined
            and (not worker_running or worker_role_drift or worker_profile_drift)
        )
        or (role == "primary" and bool(extra_running_apps))
        or (role == "primary" and proxy_upstream_drift)
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
            return None

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

        # Re-read after the lock because a candidate may have promoted meanwhile.
        service = app_service(config)
        running = compose.running_services()
        release_fenced = compose.enforce_worker_release_fence(
            COMMUNICATIONS_WORKER_SERVICE, latched=release_fenced
        )
        worker_state = _communications_worker_contract_state(
            config,
            role,
            compose=compose,
            running_services=running,
            release_fenced=release_fenced,
        )
        worker_defined = worker_state.defined
        worker_running = worker_state.running
        worker_role_matches = worker_state.role_matches
        worker_profile_drift = not worker_state.canonical_profile_matches
        if not worker_running:
            running.discard(COMMUNICATIONS_WORKER_SERVICE)
        app_running = service in running
        extra_running_apps = sorted(
            name for name in APP_SERVICE_NAMES if name != service and name in running
        )
        bot_running = "bot" in running

        if bot_running:
            compose.stop_service_verified("bot")
            bot_running = False
            actions.append("stop_legacy_bot")

        app_needs_start = fast_fenced or app_env_changed or role_changed or not app_running
        if role == "standby":
            if not systemd_matches:
                _reconcile_primary_systemd_units(config, role)
                actions.append("stop_primary_units")
            for running_app in APP_SERVICE_NAMES:
                if running_app != service and running_app in running:
                    compose.stop_service_verified(running_app)
                    actions.append("stop_extra_app")
            if app_needs_start:
                recreate_app = fast_fenced or app_env_changed or role_changed
                compose.start_service(service, recreate=recreate_app)
                actions.append(
                    "recreate_app" if recreate_app else "start_app"
                )
                if compose.refresh_container_proxy_dns(running_services=running):
                    actions.append("refresh_container_proxy_dns")
            if worker_defined and (
                fast_fenced
                or app_env_changed
                or role_changed
                or not worker_running
                or not worker_role_matches
                or worker_profile_drift
            ):
                recreate_worker = (
                    fast_fenced
                    or app_env_changed
                    or role_changed
                    or not worker_role_matches
                    or worker_profile_drift
                )
                compose.start_service(
                    COMMUNICATIONS_WORKER_SERVICE,
                    recreate=recreate_worker,
                )
                actions.append(
                    "recreate_communications_worker"
                    if recreate_worker
                    else "start_communications_worker"
                )
            final_running = compose.running_services()
            release_fenced = compose.enforce_worker_release_fence(
                COMMUNICATIONS_WORKER_SERVICE, latched=release_fenced
            )
            final_worker_state = _communications_worker_contract_state(
                config,
                role,
                compose=compose,
                running_services=final_running,
                release_fenced=release_fenced,
            )
            if (
                final_worker_state.unsafe_mismatch
                or not final_worker_state.canonical_profile_matches
                or (worker_defined and not final_worker_state.running)
            ):
                _fence_lost_primary(config)
                raise RuntimeError(
                    "standby communications worker role postcondition failed"
                )
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
                compose.start_service(service, recreate=app_env_changed)
                actions.append("recreate_app" if app_env_changed else "start_app")
                running = compose.running_services()
            proxy_upstream_changed = not compose.container_proxy_upstream_matches(
                service,
                running_services=running,
            )
            if proxy_upstream_changed:
                _require_fresh_primary_or_fence(config, "proxy_convergence")
                compose.reconcile_container_proxy_upstream(
                    service,
                    running_services=running,
                )
                actions.append("write_proxy_upstream")
            if app_needs_start or proxy_upstream_changed:
                if compose.refresh_container_proxy_dns(running_services=running):
                    actions.append("refresh_container_proxy_dns")
            if app_needs_start or proxy_upstream_changed:
                _wait_ready(config)
                actions.append("wait_ready")
            worker_needs_start = worker_defined and (
                app_env_changed
                or role_changed
                or not worker_running
                or not worker_role_matches
                or worker_role_drift
                or worker_profile_drift
            )
            if worker_needs_start:
                # Activation follows both writable API readiness and fresh DCS proof.
                if not (app_needs_start or proxy_upstream_changed):
                    _wait_ready(config)
                    actions.append("wait_ready_for_communications_worker")
                _require_fresh_primary_or_fence(
                    config,
                    "communications_worker_activation",
                )
                recreate_worker = (
                    worker_role_drift
                    or worker_profile_drift
                    or not worker_role_matches
                )
                recreate_worker = recreate_worker or role_changed or app_env_changed
                compose.start_service(
                    COMMUNICATIONS_WORKER_SERVICE,
                    recreate=recreate_worker,
                )
                actions.append(
                    "recreate_communications_worker"
                    if recreate_worker
                    else "start_communications_worker"
                )
            if extra_running_apps:
                _require_fresh_primary_or_fence(config, "extra_app_fence")
                for running_app in extra_running_apps:
                    compose.stop_service_verified(running_app)
                    actions.append("stop_extra_app")
            if (
                service in {"app-blue", "app-green"}
                and (app_needs_start or proxy_upstream_changed or extra_running_apps)
            ):
                _wait_scheduler_running(config)
                actions.append("wait_scheduler_running")
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
            final_running = compose.running_services()
            release_fenced = compose.enforce_worker_release_fence(
                COMMUNICATIONS_WORKER_SERVICE, latched=release_fenced
            )
            final_worker_state = _communications_worker_contract_state(
                config,
                role,
                compose=compose,
                running_services=final_running,
                release_fenced=release_fenced,
            )
            if (
                final_worker_state.unsafe_mismatch
                or not final_worker_state.canonical_profile_matches
                or (worker_defined and not final_worker_state.running)
            ):
                if COMMUNICATIONS_WORKER_SERVICE in final_running:
                    compose.stop_service_verified(COMMUNICATIONS_WORKER_SERVICE)
                raise RuntimeError(
                    "primary communications worker role postcondition failed"
                )
            if (
                service not in final_running
                or "bot" in final_running
                or any(
                    name in final_running for name in APP_SERVICE_NAMES if name != service
                )
                or not compose.container_proxy_upstream_matches(
                    service,
                    running_services=final_running,
                )
            ):
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
            changed = reconcile(config, role)
        except Exception as exc:
            print(f"patroni_role_agent_status=failed role={role} error={exc}", flush=True)
            if once:
                return 1
        if once:
            if changed is None:
                return 75
            print(f"patroni_role_agent_once_status=verified role={role}", flush=True)
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
