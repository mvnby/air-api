"""Docker Compose runtime operations used by the Patroni role agent."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

try:
    from scripts.ha.patroni_role_agent_config import (
        APP_SERVICE_NAMES,
        COMMUNICATIONS_WORKER_RELEASE_FENCE_BASENAME,
        CONTAINER_PROXY_SERVICE,
        PRODUCTION_COMPOSE_PROJECT_NAMES,
    )
except ModuleNotFoundError:
    from patroni_role_agent_config import (
        APP_SERVICE_NAMES,
        COMMUNICATIONS_WORKER_RELEASE_FENCE_BASENAME,
        CONTAINER_PROXY_SERVICE,
        PRODUCTION_COMPOSE_PROJECT_NAMES,
    )


COMMAND_TIMEOUT_SECONDS = 60
OPERATION_GUARD_PATH = Path("/usr/local/sbin/mvn_postgres_pitr_operation_guard.py")
ComposeRunner = Callable[..., subprocess.CompletedProcess[str]]
DockerRunner = Callable[..., subprocess.CompletedProcess[str]]
AtomicWriter = Callable[..., None]
CONTAINER_ID_PATTERN = re.compile(r"^[0-9a-f]{12,64}$")
ServiceDefinitionProbe = Callable[..., bool]
WorkerRoleProbe = Callable[..., bool]


class RuntimeConfig(Protocol):
    project_dir: Path
    compose_file: str
    ready_url: str
    ready_attempts: int


@dataclass(frozen=True)
class WorkerRuntimeState:
    defined: bool
    running: bool
    role_matches: bool
    unsafe_mismatch: bool


def run_compose(
    config: RuntimeConfig,
    *args: str,
    check: bool = True,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    command = [
        "docker",
        "compose",
        "--profile",
        "bluegreen",
        "-f",
        config.compose_file,
        *args,
    ]
    return subprocess.run(
        command,
        cwd=config.project_dir,
        check=check,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def run_docker(
    *args: str,
    check: bool = True,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


class ComposeRuntime:
    """Bound Compose operations with injectable command and file-write seams."""

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        compose_runner: ComposeRunner = run_compose,
        docker_runner: DockerRunner = run_docker,
        atomic_writer: AtomicWriter,
    ) -> None:
        self.config = config
        self.compose_runner = compose_runner
        self.docker_runner = docker_runner
        self.atomic_writer = atomic_writer

    def compose_project_name(self) -> str:
        reviewed_name = PRODUCTION_COMPOSE_PROJECT_NAMES.get(
            self.config.project_dir.resolve()
        )
        return reviewed_name or self.config.project_dir.name

    def worker_release_fence_active(self) -> bool:
        marker = (
            self.config.project_dir
            / COMMUNICATIONS_WORKER_RELEASE_FENCE_BASENAME
        )
        return marker.exists() or marker.is_symlink()

    def enforce_worker_release_fence(
        self,
        service: str,
        *,
        latched: bool = False,
    ) -> bool:
        active = latched or self.worker_release_fence_active()
        if active:
            self.fence_labeled_service_containers(service)
        return active

    def labeled_service_container_ids(self, service: str) -> tuple[str, ...]:
        result = self.docker_runner(
            "ps",
            "--all",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={self.compose_project_name()}",
            "--filter",
            f"label=com.docker.compose.service={service}",
            check=False,
            timeout=10,
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "docker ps failed").strip()
            raise RuntimeError(error)
        container_ids = tuple(
            value.strip() for value in result.stdout.splitlines() if value.strip()
        )
        if any(not CONTAINER_ID_PATTERN.fullmatch(value) for value in container_ids):
            raise RuntimeError("docker ps returned an invalid container identity")
        return container_ids

    def fence_labeled_service_containers(self, service: str) -> bool:
        """Remove only containers with this project's exact Compose service label."""

        fenced = False
        for _ in range(2):
            container_ids = self.labeled_service_container_ids(service)
            if not container_ids:
                return fenced
            fenced = True
            for container_id in container_ids:
                try:
                    stopped = self.docker_runner(
                        "stop",
                        "--timeout",
                        "10",
                        container_id,
                        check=False,
                        timeout=20,
                    )
                except subprocess.TimeoutExpired:
                    stopped = subprocess.CompletedProcess([], 1, "", "stop timed out")
                if stopped.returncode != 0:
                    try:
                        self.docker_runner(
                            "kill",
                            "--signal",
                            "SIGKILL",
                            container_id,
                            check=False,
                            timeout=10,
                        )
                    except subprocess.TimeoutExpired:
                        pass
                try:
                    self.docker_runner(
                        "rm",
                        "--force",
                        container_id,
                        check=False,
                        timeout=20,
                    )
                except subprocess.TimeoutExpired:
                    pass
        remaining = self.labeled_service_container_ids(service)
        if remaining:
            raise RuntimeError(
                f"could not fence labeled Compose service {service}: "
                f"{len(remaining)} container(s) remain"
            )
        return fenced

    def worker_runtime_state(
        self,
        *,
        service: str,
        role: str,
        running_services: set[str],
        definition_probe: ServiceDefinitionProbe,
        role_probe: WorkerRoleProbe,
        release_fenced: bool = False,
    ) -> WorkerRuntimeState:
        if release_fenced:
            return WorkerRuntimeState(False, False, True, False)
        try:
            defined = definition_probe(
                self.config,
                service,
                compose_runner=self.compose_runner,
            )
        except Exception:
            self.fence_labeled_service_containers(service)
            raise
        running = service in running_services
        if not defined:
            # The candidate transaction starts the new service before atomically
            # promoting its Compose file. The old canonical agent must ignore
            # that same-project orphan during this bounded rollout window.
            return WorkerRuntimeState(False, False, False, False)
        if not running:
            return WorkerRuntimeState(True, False, True, False)
        try:
            role_matches = role_probe(
                self.config,
                role,
                compose_runner=self.compose_runner,
            )
        except Exception:
            self.fence_labeled_service_containers(service)
            return WorkerRuntimeState(True, False, False, True)
        if not role_matches:
            self.fence_labeled_service_containers(service)
            return WorkerRuntimeState(True, False, False, True)
        return WorkerRuntimeState(
            True,
            True,
            True,
            False,
        )

    def running_services(self) -> set[str]:
        result = self.compose_runner(
            self.config,
            "ps",
            "--status",
            "running",
            "--format",
            "json",
            check=False,
        )
        if result.returncode != 0:
            error = (
                result.stderr or result.stdout or "docker compose ps failed"
            ).strip()
            raise RuntimeError(error)
        payload = result.stdout.strip()
        if not payload:
            return set()
        try:
            parsed = json.loads(payload)
            records = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            try:
                records = [
                    json.loads(line) for line in payload.splitlines() if line.strip()
                ]
            except json.JSONDecodeError as exc:
                raise RuntimeError("docker compose ps returned invalid JSON") from exc

        services: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                raise RuntimeError("docker compose ps returned an invalid record")
            service = record.get("Service")
            labels = record.get("Labels", "")
            if not isinstance(service, str) or not service:
                raise RuntimeError("docker compose ps record is missing its service")
            if isinstance(labels, dict):
                oneoff = str(labels.get("com.docker.compose.oneoff", "")).lower()
            elif isinstance(labels, str):
                oneoff = next(
                    (
                        value.lower()
                        for label in labels.split(",")
                        if "=" in label
                        for key, value in [label.split("=", 1)]
                        if key == "com.docker.compose.oneoff"
                    ),
                    "",
                )
            else:
                raise RuntimeError("docker compose ps record has invalid labels")
            if oneoff not in {"true", "false"}:
                raise RuntimeError(
                    "docker compose ps record is missing its one-off identity"
                )
            if oneoff == "false":
                services.add(service)
        return services

    def start_service(self, service: str, *, recreate: bool) -> None:
        args = ["up", "-d", "--no-deps"]
        if recreate:
            args.append("--force-recreate")
        args.append(service)
        self.compose_runner(self.config, *args)

    def refresh_container_proxy_dns(self, *, running_services: set[str]) -> bool:
        """Refresh nginx's startup-time Docker DNS after an app changes."""

        if CONTAINER_PROXY_SERVICE not in running_services:
            return False
        self.compose_runner(self.config, "restart", CONTAINER_PROXY_SERVICE)
        return True

    def proxy_upstream_path(self) -> Path:
        return self.config.project_dir / "api-proxy" / "upstream.conf"

    @staticmethod
    def expected_proxy_upstream(service: str) -> str:
        if service not in APP_SERVICE_NAMES:
            raise ValueError(f"unsupported API app service: {service}")
        return f"proxy_pass http://{service}:8000;\n"

    def container_proxy_upstream_matches(
        self,
        service: str,
        *,
        running_services: set[str],
    ) -> bool:
        if CONTAINER_PROXY_SERVICE not in running_services:
            return True
        try:
            current = self.proxy_upstream_path().read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return False
        return current == self.expected_proxy_upstream(service)

    def reconcile_container_proxy_upstream(
        self,
        service: str,
        *,
        running_services: set[str],
    ) -> bool:
        if self.container_proxy_upstream_matches(
            service,
            running_services=running_services,
        ):
            return False
        self.atomic_writer(
            self.proxy_upstream_path(),
            self.expected_proxy_upstream(service),
            mode=0o644,
        )
        return True

    def stop_service_verified(self, service: str) -> None:
        error = ""
        try:
            removed = self.compose_runner(
                self.config,
                "rm",
                "--stop",
                "--force",
                service,
                check=False,
                timeout=20,
            )
            error = (removed.stderr or removed.stdout).strip()
        except subprocess.TimeoutExpired:
            error = "container removal timed out"
        try:
            remaining = self.compose_runner(
                self.config,
                "ps",
                "--all",
                "--quiet",
                service,
                check=False,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            remaining = subprocess.CompletedProcess(
                [], 1, "", "container inventory timed out"
            )
        if remaining.returncode == 0 and not remaining.stdout.strip():
            return
        try:
            self.compose_runner(
                self.config,
                "kill",
                "--signal",
                "SIGKILL",
                service,
                check=False,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            pass
        try:
            forced = self.compose_runner(
                self.config,
                "rm",
                "--force",
                service,
                check=False,
                timeout=20,
            )
            error = (forced.stderr or forced.stdout or error).strip()
        except subprocess.TimeoutExpired:
            error = "forced container removal timed out"
        final = self.compose_runner(
            self.config,
            "ps",
            "--all",
            "--quiet",
            service,
            check=False,
            timeout=10,
        )
        if final.returncode != 0 or final.stdout.strip():
            raise RuntimeError(
                f"could not fence Compose service {service}: "
                f"{error or 'container remains'}"
            )


def wait_scheduler_running(config: RuntimeConfig) -> None:
    for _ in range(config.ready_attempts):
        try:
            with urllib.request.urlopen(config.ready_url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            runtime = payload.get("scheduler_runtime")
            if (
                response.status == 200
                and payload.get("api") == "ready"
                and payload.get("database_writable") is True
                and isinstance(runtime, dict)
                and runtime.get("expected") is True
                and runtime.get("status") == "running"
            ):
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise RuntimeError(
        f"primary scheduler did not acquire runtime ownership: {config.ready_url}"
    )


def cancel_pitr_operations(config: RuntimeConfig) -> list[str]:
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
