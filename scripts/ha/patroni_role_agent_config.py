"""Reviewed configuration contract for the Patroni API role agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.ha.patroni_local_identity import fetch_patroni_role, integer_env
except ModuleNotFoundError:
    from patroni_local_identity import fetch_patroni_role, integer_env


EXPECTED_LOCAL_PATRONI_URL = "http://127.0.0.1:8008/patroni"
EXPECTED_PATRONI_SCOPE = "mvn-postgres"
DEFAULT_MAX_DCS_AGE_SECONDS = 20
MAX_CONFIGURED_DCS_AGE_SECONDS = 20
PRODUCTION_NODE_NAMES = {
    Path("/opt/air-api"): "mvn-api",
    Path("/opt/mvn-reserve"): "zakup",
}
PRODUCTION_COMPOSE_PROJECT_NAMES = {
    Path("/opt/air-api"): "air-api",
    Path("/opt/mvn-reserve"): "mvn_reserve",
}
REVIEWED_PRIMARY_SYSTEMD_UNITS = (
    "mvn-postgres-wal-upload.timer",
    "mvn-postgres-basebackup.timer",
)
APP_SERVICE_NAMES = ("app", "app-blue", "app-green")
CONTAINER_PROXY_SERVICE = "api-proxy"
COMMUNICATIONS_WORKER_RELEASE_FENCE_BASENAME = (
    ".ha-communications-worker-release-fenced"
)


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


def fetch_configured_patroni_role(config: AgentConfig) -> str:
    return fetch_patroni_role(
        config.patroni_url,
        expected_name=config.patroni_name,
        expected_scope=config.patroni_scope,
        max_dcs_age_seconds=config.max_dcs_age_seconds,
    )


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
        raise ValueError(
            f"HA_PROJECT_DIR is not a reviewed Patroni node path: {project_dir}"
        )
    if patroni_name != inferred_patroni_name:
        raise ValueError(
            f"HA_PATRONI_NAME must be {inferred_patroni_name} for {project_dir}"
        )
    max_dcs_age_seconds = integer_env(
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
        poll_seconds=integer_env("HA_ROLE_POLL_SECONDS", 3),
        promotion_delay_seconds=integer_env(
            "HA_PROMOTION_DELAY_SECONDS", 8, minimum=0
        ),
        ready_attempts=integer_env("HA_READY_ATTEMPTS", 30),
    )
