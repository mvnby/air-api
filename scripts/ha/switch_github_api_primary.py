#!/usr/bin/env python3
"""Switch GitHub Actions API primary/standby routing variables.

Use this after a real PostgreSQL promotion/failback decision. By default the
helper prints the exact GitHub secret/variable writes and does not modify
anything. Pass --confirm to apply.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence


DEFAULT_REPO = "mvnby/air-api"

Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ApiHostProfile:
    name: str
    origin: str
    project_dir: str
    compose_file: str
    primary_compose_source: str
    standby_compose_source: str
    primary_local_port: int
    standby_local_port: int
    deploy_strategy: str

    @property
    def base_url(self) -> str:
        return f"http://localhost:{self.primary_local_port}"

    @property
    def local_health_url(self) -> str:
        return f"http://127.0.0.1:{self.primary_local_port}/api/health"

    @property
    def ready_url(self) -> str:
        return f"http://localhost:{self.primary_local_port}/api/ready"

    @property
    def health_url(self) -> str:
        return f"http://localhost:{self.primary_local_port}/api/health"

    @property
    def standby_health_url(self) -> str:
        return f"http://localhost:{self.standby_local_port}/api/health"


HOSTS = {
    "mvn-api": ApiHostProfile(
        name="mvn-api",
        origin="185.250.45.54",
        project_dir="/opt/air-api",
        compose_file="docker-compose.prod.yml",
        primary_compose_source="deploy/ha/mvn-api/docker-compose.primary.yml",
        standby_compose_source="deploy/ha/mvn-api/docker-compose.standby.yml",
        primary_local_port=18080,
        standby_local_port=8000,
        deploy_strategy="blue_green",
    ),
    "zakup": ApiHostProfile(
        name="zakup",
        origin="193.47.42.213",
        project_dir="/opt/mvn-reserve",
        compose_file="docker-compose.reserve.yml",
        primary_compose_source="deploy/ha/zakup/docker-compose.primary.yml",
        standby_compose_source="deploy/ha/zakup/docker-compose.standby.yml",
        primary_local_port=18000,
        standby_local_port=18000,
        deploy_strategy="in_place",
    ),
}


def log(stage: str, message: str) -> None:
    print(f"[github-api-primary][{stage}] {message}")


def _run_subprocess(args: Sequence[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def run_checked(args: Sequence[str], *, stdin: str | None = None, runner: Runner | None = None) -> str:
    actual_runner = runner or _run_subprocess
    result = actual_runner(args, stdin)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(output or f"command failed: {' '.join(args)}")
    return result.stdout.strip()


def opposite_host(name: str) -> str:
    if name == "mvn-api":
        return "zakup"
    if name == "zakup":
        return "mvn-api"
    raise RuntimeError(f"unknown API host profile: {name}")


def build_routing(primary_name: str) -> tuple[str, Mapping[str, str]]:
    primary = HOSTS[primary_name]
    standby = HOSTS[opposite_host(primary_name)]
    variables = {
        # Physical Patroni node identity never changes during a role switch.
        # Monitoring workflows must not infer these values from the dynamic
        # primary/standby routing variables below.
        "PATRONI_MVN_API_HOST": HOSTS["mvn-api"].origin,
        "PATRONI_ZAKUP_HOST": HOSTS["zakup"].origin,
        "API_PRIMARY_ORIGIN": primary.origin,
        "API_STANDBY_ORIGIN": standby.origin,
        "API_PROJECT_DIR": primary.project_dir,
        "API_COMPOSE_FILE": primary.compose_file,
        "API_COMPOSE_SOURCE_FILE": primary.primary_compose_source,
        "API_COPY_COMPOSE": "true",
        "API_DEPLOY_STRATEGY": primary.deploy_strategy,
        "API_BASE_URL": primary.base_url,
        "API_READY_URL": primary.ready_url,
        "API_LOCAL_HEALTH_URL": primary.local_health_url,
        "API_TUNNEL_REMOTE_PORT": str(primary.primary_local_port),
        "API_DEPLOY_SERVICES": "app",
        "API_SMOKE_COMPOSE_SERVICE_CHECKS": "app db",
        "API_COMPOSE_SERVICE_CHECKS": "app db",
        "API_BOT_EXPECT_ENABLED": "false",
        "API_STANDBY_HOST": standby.origin,
        "API_STANDBY_PROJECT_DIR": standby.project_dir,
        "API_STANDBY_COMPOSE_FILE": standby.compose_file,
        "API_STANDBY_COPY_COMPOSE": "true",
        "API_STANDBY_COMPOSE_SOURCE_FILE": standby.standby_compose_source,
        "API_STANDBY_HEALTH_URL": standby.standby_health_url,
    }
    return primary.origin, variables


def set_secret(repo: str, name: str, value: str, *, runner: Runner | None = None) -> None:
    run_checked(["gh", "secret", "set", name, "--repo", repo], stdin=f"{value}\n", runner=runner)
    log("ok", f"GitHub secret set: {name}")


def set_variable(repo: str, name: str, value: str, *, runner: Runner | None = None) -> None:
    run_checked(["gh", "variable", "set", name, "--repo", repo], stdin=f"{value}\n", runner=runner)
    log("ok", f"GitHub variable set: {name}={value}")


def print_plan(primary_name: str, ssh_host_api: str, variables: Mapping[str, str]) -> None:
    standby_name = opposite_host(primary_name)
    log("plan", f"primary={primary_name} standby={standby_name}")
    log("plan", f"secret SSH_HOST_API={ssh_host_api}")
    for name in sorted(variables):
        log("plan", f"variable {name}={variables[name]}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Switch GitHub Actions API deploy/check routing between mvn-api and zakup."
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument(
        "--primary",
        choices=sorted(HOSTS),
        required=True,
        help="Host that is already promoted and should receive primary deploys/checks.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Apply the printed GitHub secret/variable changes.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        ssh_host_api, variables = build_routing(args.primary)
        log("info", f"repo={args.repo}")
        print_plan(args.primary, ssh_host_api, variables)
        if not args.confirm:
            log("dry-run", "no changes applied; rerun with --confirm after reviewing the plan")
            return 0

        set_secret(args.repo, "SSH_HOST_API", ssh_host_api)
        for name in sorted(variables):
            set_variable(args.repo, name, variables[name])
        log("ok", "GitHub API routing updated")
        return 0
    except RuntimeError as exc:
        log("fail", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
