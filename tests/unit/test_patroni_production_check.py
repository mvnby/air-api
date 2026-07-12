import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.ha.check_patroni_production import (
    CheckerConfig,
    NodeConfig,
    Report,
    _check_cluster_views,
    _check_postgres,
    _parse_rows,
    role_from_patroni,
    select_primary,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _nodes() -> tuple[NodeConfig, NodeConfig]:
    return (
        NodeConfig(
            label="api",
            patroni_name="mvn-api",
            ssh_target="root@api",
            project_dir="/opt/air-api",
            compose_file="docker-compose.patroni.yml",
            wireguard_ip="10.77.0.2",
        ),
        NodeConfig(
            label="reserve",
            patroni_name="zakup",
            ssh_target="root@reserve",
            project_dir="/opt/mvn-reserve",
            compose_file="docker-compose.patroni.yml",
            wireguard_ip="10.77.0.1",
        ),
    )


def test_role_parser_requires_running_supported_role():
    assert role_from_patroni({"state": "running", "role": "primary"}) == "primary"
    assert role_from_patroni({"state": "running", "role": "replica"}) == "standby"

    with pytest.raises(ValueError, match="expected running"):
        role_from_patroni({"state": "stopped", "role": "replica"})
    with pytest.raises(ValueError, match="unsupported Patroni role"):
        role_from_patroni({"state": "running", "role": "unknown"})


def test_primary_selection_accepts_nested_patroni_names():
    api, reserve = _nodes()
    primary, standby = select_primary(
        (api, reserve),
        {
            "api": {
                "state": "running",
                "role": "primary",
                "patroni": {"name": "mvn-api"},
            },
            "reserve": {
                "state": "running",
                "role": "replica",
                "patroni": {"name": "zakup"},
            },
        },
    )

    assert primary == api
    assert standby == reserve


def test_primary_selection_rejects_split_brain_and_pending_restart():
    api, reserve = _nodes()
    both_primary = {
        "api": {"state": "running", "role": "primary", "name": "mvn-api"},
        "reserve": {"state": "running", "role": "primary", "name": "zakup"},
    }
    with pytest.raises(ValueError, match="unsafe Patroni topology"):
        select_primary((api, reserve), both_primary)

    pending_restart = {
        "api": {
            "state": "running",
            "role": "primary",
            "name": "mvn-api",
            "pending_restart": True,
        },
        "reserve": {"state": "running", "role": "replica", "name": "zakup"},
    }
    with pytest.raises(ValueError, match="pending_restart"):
        select_primary((api, reserve), pending_restart)

    failsafe = {
        "api": {
            "state": "running",
            "role": "primary",
            "name": "mvn-api",
            "failsafe_mode_is_active": True,
        },
        "reserve": {"state": "running", "role": "replica", "name": "zakup"},
    }
    with pytest.raises(ValueError, match="failsafe mode is active"):
        select_primary((api, reserve), failsafe)


def test_sql_row_parser_is_strict():
    assert _parse_rows("zakup|10.77.0.1|streaming|sync|0\n", 5) == [
        ["zakup", "10.77.0.1", "streaming", "sync", "0"]
    ]
    with pytest.raises(ValueError, match="unexpected SQL row"):
        _parse_rows("too|few", 5)


def test_patroni_monitor_strips_inet_netmask_in_sql():
    source = (REPO_ROOT / "scripts/ha/check_patroni_production.py").read_text(
        encoding="utf-8"
    )

    assert "host(client_addr)" in source
    assert "client_addr::text" not in source


def test_cluster_view_accepts_replica_role_but_requires_sync_endpoint():
    api, reserve = _nodes()
    config = CheckerConfig(
        api=api,
        reserve=reserve,
        ssh_options=(),
        max_replay_lag_bytes=1_048_576,
        role_agent_unit="mvn-patroni-role-agent.service",
        etcd_check_command="check-etcd",
        ready_url="http://127.0.0.1:18080/api/ready",
    )
    cluster = {
        "members": [
            {
                "name": "mvn-api",
                "role": "leader",
                "state": "running",
                "timeline": 2,
            },
            {
                "name": "zakup",
                "role": "replica",
                "state": "streaming",
                "timeline": 2,
                "lag": 0,
            },
        ]
    }

    class FakeRunner:
        sync_status = 0

        def run(self, node, command, *, stdin=None, check=True):
            del node, stdin, check
            if command.endswith("/cluster"):
                return subprocess.CompletedProcess([], 0, json.dumps(cluster), "")
            if "/sync" in command:
                return subprocess.CompletedProcess([], self.sync_status, "", "")
            raise AssertionError(command)

    report = Report()
    runner = FakeRunner()
    _check_cluster_views(config, runner, api, reserve, report)
    assert report.failures == []
    assert any("sync_standby=zakup" in message for message in report.ok)

    runner.sync_status = 22
    report = Report()
    _check_cluster_views(config, runner, api, reserve, report)
    assert report.failures == ["reserve: Patroni /sync endpoint is not healthy"]


def test_postgres_check_treats_negative_receiver_delta_as_zero_backlog():
    api, reserve = _nodes()
    config = CheckerConfig(
        api=api,
        reserve=reserve,
        ssh_options=(),
        max_replay_lag_bytes=1_048_576,
        role_agent_unit="mvn-patroni-role-agent.service",
        etcd_check_command="check-etcd",
        ready_url="http://127.0.0.1:18080/api/ready",
    )

    class FakeRunner:
        def run(self, node, command, *, stdin=None, check=True):
            del command, check
            statement = (stdin or "").strip()
            if statement == "select pg_is_in_recovery();":
                output = "f\n" if node == api else "t\n"
            elif statement == "select system_identifier from pg_control_system();":
                output = "7657288033494519840\n"
            elif "from pg_stat_replication" in statement:
                output = "zakup|10.77.0.1|streaming|sync|0\n"
            elif "from pg_stat_wal_receiver" in statement:
                output = "streaming|10.77.0.2|zakup|-10076160\n"
            elif statement == "show synchronous_standby_names;":
                output = "ANY 1 (zakup)\n"
            elif statement == "show wal_log_hints;":
                output = "on\n"
            elif statement == "show archive_mode;":
                output = "on\n"
            else:
                raise AssertionError(statement)
            return subprocess.CompletedProcess([], 0, output, "")

    report = Report()
    _check_postgres(config, FakeRunner(), api, reserve, report)

    assert report.failures == []
    assert any("streams synchronously" in message for message in report.ok)


def test_replication_workflow_switches_to_role_aware_patroni_monitoring():
    workflow = yaml.load(
        (REPO_ROOT / ".github/workflows/check-postgres-replication.yml").read_text(
            encoding="utf-8"
        ),
        Loader=yaml.BaseLoader,
    )
    run = next(
        step["run"]
        for step in workflow["jobs"]["check"]["steps"]
        if step.get("name") == "Run PostgreSQL replication check"
    )

    assert workflow["on"]["schedule"][0]["cron"] == "7,17,27,37,47,57 * * * *"
    assert "API_DB_HA_MODE" in run
    assert "check_patroni_production.py" in run
    assert "check_postgres_replication.sh" in run
    assert "API_NODE_SSH" in run
    assert "RESERVE_NODE_SSH" in run


def test_pitr_workflow_resolves_the_current_patroni_primary():
    workflow = yaml.load(
        (REPO_ROOT / ".github/workflows/check-postgres-pitr.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    run = next(
        step["run"]
        for step in workflow["jobs"]["check"]["steps"]
        if step.get("name") == "Run PostgreSQL PITR Check"
    )

    assert "check_patroni_production.py --resolve-primary" in run
    assert "target_label=reserve" in run
    assert "target_compose_file=docker-compose.patroni.yml" in run
    assert "API_DB_HA_MODE must be physical or patroni" in run


def test_api_vps_health_workflow_targets_current_patroni_primary():
    workflow = yaml.load(
        (REPO_ROOT / ".github/workflows/check-api-vps-health.yml").read_text(
            encoding="utf-8"
        ),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["check"]["steps"]
    setup = next(step for step in steps if step.get("name") == "Setup API SSH Key")
    check = next(step for step in steps if step.get("name") == "Run API VPS Health Check")

    assert "API_STANDBY_HOST" in setup["env"]
    assert '"${API_STANDBY_HOST}"' in setup["run"]
    assert "API_DB_HA_MODE" in check["env"]
    assert "check_patroni_production.py --resolve-primary" in check["run"]
    assert 'target_host="${API_STANDBY_HOST}"' in check["run"]
    assert "API_DB_HA_MODE must be physical or patroni" in check["run"]
