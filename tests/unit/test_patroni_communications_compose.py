from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PRIMARY_COMPOSE = REPO_ROOT / "deploy/ha/mvn-api/docker-compose.patroni.yml"
RESERVE_COMPOSE = REPO_ROOT / "deploy/ha/zakup/docker-compose.patroni.yml"
IMMUTABLE_BACKEND_IMAGE = "${BACKEND_IMAGE:?set immutable BACKEND_IMAGE in .env}"
WORKER_COMMAND = "python -m services.communications.runtime"


@pytest.mark.parametrize(
    ("compose_path", "expected_env_file", "expected_database_url", "expected_memory"),
    [
        (
            PRIMARY_COMPOSE,
            [".env", ".ha-app-role.env"],
            (
                "postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}"
                "@db/${POSTGRES_DB}"
            ),
            "${MVN_PATRONI_COMMUNICATIONS_WORKER_MEMORY:-256m}",
        ),
        (
            RESERVE_COMPOSE,
            ["${MVN_RESERVE_ENV_FILE:-.env}", ".ha-app-role.env"],
            (
                "postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}"
                "@db/${POSTGRES_DB:-air_conditioners}"
            ),
            "${MVN_RESERVE_COMMUNICATIONS_WORKER_MEMORY:-256m}",
        ),
    ],
)
def test_patroni_communications_worker_is_dormant_and_role_driven(
    compose_path: Path,
    expected_env_file: list[str],
    expected_database_url: str,
    expected_memory: str,
) -> None:
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose["services"]
    worker = services["communications-worker"]

    assert worker["image"] == services["app"]["image"] == IMMUTABLE_BACKEND_IMAGE
    assert worker["command"] == WORKER_COMMAND
    assert worker["restart"] == "unless-stopped"
    assert worker["depends_on"] == {"db": {"condition": "service_healthy"}}
    assert worker["env_file"] == services["app"]["env_file"] == expected_env_file
    assert worker["environment"] == {
        "DATABASE_URL": expected_database_url,
        "ENVIRONMENT": "production",
        "COMMUNICATIONS_WORKER_ENABLED": "false",
        "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE": "false",
    }
    assert (
        worker["environment"]["DATABASE_URL"]
        == services["app"]["environment"]["DATABASE_URL"]
    )
    assert "APP_ROLE" not in worker["environment"]
    assert worker["mem_limit"] == expected_memory


@pytest.mark.parametrize("compose_path", [PRIMARY_COMPOSE, RESERVE_COMPOSE])
def test_patroni_communications_worker_has_no_public_or_host_storage_surface(
    compose_path: Path,
) -> None:
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    worker = compose["services"]["communications-worker"]

    assert "ports" not in worker
    assert "volumes" not in worker
    assert "privileged" not in worker
    assert "devices" not in worker
    assert "network_mode" not in worker
    assert "profiles" not in worker
    assert "cap_add" not in worker
    assert "pid" not in worker
    assert "ipc" not in worker


def test_reserve_communications_worker_stays_on_the_private_reserve_network() -> None:
    compose = yaml.safe_load(RESERVE_COMPOSE.read_text(encoding="utf-8"))

    assert compose["services"]["communications-worker"]["networks"] == ["reserve"]
