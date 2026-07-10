from pathlib import Path

import pytest
import yaml

from deploy.ha.patroni.render_patroni_config import render_config


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "deploy/ha/patroni/Dockerfile"
ENTRYPOINT = REPO_ROOT / "deploy/ha/patroni/patroni-entrypoint.sh"
REHEARSAL_COMPOSE = REPO_ROOT / "deploy/ha/patroni/rehearsal/docker-compose.yml"
REHEARSAL = REPO_ROOT / "scripts/ha/rehearse_patroni_failover.sh"
REHEARSAL_WORKFLOW = REPO_ROOT / ".github/workflows/patroni-failover-rehearsal.yml"
PUBLISH_WORKFLOW = REPO_ROOT / ".github/workflows/publish-patroni-image.yml"
PRIMARY_COMPOSE = REPO_ROOT / "deploy/ha/mvn-api/docker-compose.patroni.yml"
RESERVE_COMPOSE = REPO_ROOT / "deploy/ha/zakup/docker-compose.patroni.yml"
PROXY_CONFIG = REPO_ROOT / "deploy/ha/proxy/nginx.conf"


@pytest.fixture
def patroni_env(monkeypatch):
    values = {
        "PATRONI_NAME": "pg1",
        "PATRONI_POSTGRESQL_CONNECT_ADDRESS": "10.77.0.2:5432",
        "PATRONI_RESTAPI_CONNECT_ADDRESS": "10.77.0.2:8008",
        "PATRONI_ETCD3_HOSTS": "10.77.0.1:2379,10.77.0.2:2379,10.77.0.3:2379",
        "PATRONI_ETCD3_PROTOCOL": "https",
        "PATRONI_ETCD3_CACERT": "/etc/etcd/pki/ca.crt",
        "PATRONI_ETCD3_CERT": "/etc/etcd/pki/node.crt",
        "PATRONI_ETCD3_KEY": "/etc/etcd/pki/node.key",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "password: with spaces",
        "PATRONI_REPLICATION_PASSWORD": "replication: secret",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_renderer_builds_synchronous_tls_patroni_config(patroni_env):
    config = render_config()

    assert config["name"] == "pg1"
    assert config["etcd3"]["protocol"] == "https"
    assert len(config["etcd3"]["hosts"]) == 3
    dcs = config["bootstrap"]["dcs"]
    assert dcs["synchronous_mode"] is True
    assert dcs["synchronous_mode_strict"] is False
    assert dcs["failsafe_mode"] is True
    assert dcs["postgresql"]["use_pg_rewind"] is True
    assert config["postgresql"]["authentication"]["superuser"]["password"] == (
        patroni_env["POSTGRES_PASSWORD"]
    )
    assert config["watchdog"]["mode"] == "off"


def test_renderer_rejects_unsafe_timing_budget(patroni_env, monkeypatch):
    monkeypatch.setenv("PATRONI_TTL", "20")
    monkeypatch.setenv("PATRONI_LOOP_WAIT", "10")
    monkeypatch.setenv("PATRONI_RETRY_TIMEOUT", "10")

    with pytest.raises(ValueError, match="must be <="):
        render_config()


def test_renderer_normalizes_postgres_archive_timeout_seconds(patroni_env, monkeypatch):
    monkeypatch.setenv("PATRONI_ARCHIVE_MODE", "on")
    monkeypatch.setenv("PATRONI_ARCHIVE_TIMEOUT", "300s")
    monkeypatch.setenv("PATRONI_ARCHIVE_COMMAND", "cp %p /archive/%f")

    config = render_config()

    parameters = config["bootstrap"]["dcs"]["postgresql"]["parameters"]
    assert parameters["archive_timeout"] == 300


def test_renderer_rejects_non_second_archive_timeout(patroni_env, monkeypatch):
    monkeypatch.setenv("PATRONI_ARCHIVE_MODE", "on")
    monkeypatch.setenv("PATRONI_ARCHIVE_TIMEOUT", "5min")
    monkeypatch.setenv("PATRONI_ARCHIVE_COMMAND", "cp %p /archive/%f")

    with pytest.raises(ValueError, match="integer seconds"):
        render_config()


def test_patroni_image_and_entrypoint_are_versioned_and_adoption_safe():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert "postgres:15.18-alpine@sha256:" in dockerfile
    assert "PATRONI_VERSION=4.1.4" in dockerfile
    assert '"patroni[etcd3]==${PATRONI_VERSION}"' in dockerfile
    assert "PATRONI_ALLOW_BOOTSTRAP" in entrypoint
    assert "PGDATA is empty" in entrypoint
    assert 'chmod 0700 "${PGDATA}"' in entrypoint
    assert "chown -R" not in entrypoint
    assert "su-exec postgres" in entrypoint


def test_rehearsal_is_isolated_and_exercises_failover_and_rejoin():
    compose = yaml.safe_load(REHEARSAL_COMPOSE.read_text(encoding="utf-8"))
    compose_text = REHEARSAL_COMPOSE.read_text(encoding="utf-8")
    text = REHEARSAL.read_text(encoding="utf-8")

    assert compose["name"] == "mvn_patroni_rehearsal"
    assert {"etcd1", "etcd2", "etcd3", "pg1", "pg2"} <= set(compose["services"])
    assert compose["services"]["pg1"]["ports"] == ["127.0.0.1:55431:5432", "127.0.0.1:18008:8008"]
    assert compose["services"]["pg2"]["ports"] == ["127.0.0.1:55432:5432", "127.0.0.1:18009:8008"]
    assert "PATRONI_ETCD3_HOSTS" in compose_text
    assert "PATRONI_ETCD_HOSTS" not in compose_text
    assert "down -v --remove-orphans" in text
    assert 'stop "${leader}"' in text
    assert "http://127.0.0.1:8008/patroni" in text
    assert 'exec -T \\\n    -e "PGOPTIONS=' in text
    assert "replica was not registered as synchronous" in text
    assert "pg_stat_replication" in text
    assert "former leader did not rejoin" in text
    assert "stop etcd3" in text


def test_rehearsal_workflow_is_scheduled_and_keeps_logs():
    workflow = yaml.load(REHEARSAL_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["rehearse"]
    steps = {step["name"]: step for step in job["steps"]}

    assert "schedule" in workflow["on"]
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    assert "rehearse_patroni_failover.sh" in steps["Run isolated Patroni failover rehearsal"]["run"]
    assert steps["Upload rehearsal log"]["if"] == "${{ always() }}"
    assert "production_data_touched: false" in steps["Rehearsal summary"]["run"]


def test_production_patroni_composes_are_role_driven_and_private():
    primary = yaml.safe_load(PRIMARY_COMPOSE.read_text(encoding="utf-8"))
    reserve = yaml.safe_load(RESERVE_COMPOSE.read_text(encoding="utf-8"))

    for compose, address in ((primary, "10.77.0.2"), (reserve, "10.77.0.1")):
        db = compose["services"]["db"]
        assert db["image"] == "${PATRONI_IMAGE:?set immutable PATRONI_IMAGE in .env}"
        assert db["environment"]["PATRONI_ALLOW_BOOTSTRAP"] == "false"
        assert db["environment"]["PATRONI_SYNCHRONOUS_MODE"] == "true"
        assert db["environment"]["PATRONI_SYNCHRONOUS_MODE_STRICT"] == "false"
        assert db["environment"]["PATRONI_ETCD3_PROTOCOL"] == "https"
        assert f"{address}:5432:5432" in db["ports"]
        assert f"{address}:8008:8008" in db["ports"]
        assert "0.0.0.0:5432:5432" not in db["ports"]
        assert compose["services"]["app-blue"]["env_file"][-1] == ".ha-app-role.env"
        assert compose["services"]["bot"]["env_file"][-1] == ".ha-bot-role.env"

    assert reserve["services"]["api-proxy"]["ports"] == ["127.0.0.1:18080:8000"]
    assert "proxy_set_header Host api.mvn.by" in PROXY_CONFIG.read_text(encoding="utf-8")


def test_patroni_image_publish_is_manual_sha_gated_and_digest_pinned():
    workflow = yaml.load(PUBLISH_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["publish"]
    steps = {step["name"]: step for step in job["steps"]}

    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert "No successful CI run found" in steps["Require tested main SHA"]["run"]
    assert steps["Checkout exact tested SHA"]["with"]["ref"] == "${{ github.sha }}"
    build = steps["Build and push Patroni"]["with"]
    assert build["file"] == "deploy/ha/patroni/Dockerfile"
    assert build["platforms"] == "linux/amd64"
    assert build["provenance"] == "mode=max"
    assert build["sbom"] == "true"
    assert "patroni@${digest}" in steps["Resolve immutable image"]["run"]
