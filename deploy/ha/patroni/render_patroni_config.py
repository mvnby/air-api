#!/usr/bin/env python3
"""Render a validated Patroni YAML file from environment variables."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def boolean(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def integer(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def seconds(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw.endswith("s"):
        raw = raw[:-1].strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be integer seconds, optionally suffixed with s") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def csv(name: str) -> list[str]:
    values = [item.strip() for item in required(name).split(",") if item.strip()]
    if not values:
        raise ValueError(f"{name} must contain at least one value")
    return values


def render_config() -> dict[str, Any]:
    scope = os.getenv("PATRONI_SCOPE", "mvn-postgres").strip() or "mvn-postgres"
    name = required("PATRONI_NAME")
    connect_address = required("PATRONI_POSTGRESQL_CONNECT_ADDRESS")
    rest_connect_address = required("PATRONI_RESTAPI_CONNECT_ADDRESS")
    etcd_protocol = os.getenv("PATRONI_ETCD3_PROTOCOL", "https").strip().lower()
    if etcd_protocol not in {"http", "https"}:
        raise ValueError("PATRONI_ETCD3_PROTOCOL must be http or https")

    ttl = integer("PATRONI_TTL", 30, minimum=20)
    loop_wait = integer("PATRONI_LOOP_WAIT", 10, minimum=1)
    retry_timeout = integer("PATRONI_RETRY_TIMEOUT", 10, minimum=1)
    if loop_wait + (2 * retry_timeout) > ttl:
        raise ValueError("PATRONI_LOOP_WAIT + 2*PATRONI_RETRY_TIMEOUT must be <= PATRONI_TTL")

    superuser = required("POSTGRES_USER")
    superuser_password = required("POSTGRES_PASSWORD")
    replication_user = os.getenv("PATRONI_REPLICATION_USERNAME", "mvn_replicator").strip()
    replication_password = required("PATRONI_REPLICATION_PASSWORD")
    data_dir = os.getenv("PATRONI_POSTGRESQL_DATA_DIR", "/var/lib/postgresql/data").strip()
    pgpass = os.getenv("PATRONI_POSTGRESQL_PGPASS", "/tmp/pgpass").strip()

    etcd3: dict[str, Any] = {
        "hosts": csv("PATRONI_ETCD3_HOSTS"),
        "protocol": etcd_protocol,
    }
    if etcd_protocol == "https":
        etcd3.update(
            {
                "cacert": required("PATRONI_ETCD3_CACERT"),
                "cert": required("PATRONI_ETCD3_CERT"),
                "key": required("PATRONI_ETCD3_KEY"),
            }
        )

    postgres_parameters: dict[str, Any] = {
        "hot_standby": "on",
        "max_connections": integer("PATRONI_MAX_CONNECTIONS", 100, minimum=20),
        "max_replication_slots": integer("PATRONI_MAX_REPLICATION_SLOTS", 10, minimum=2),
        "max_wal_senders": integer("PATRONI_MAX_WAL_SENDERS", 10, minimum=2),
        "unix_socket_directories": "/var/run/postgresql",
        "wal_keep_size": os.getenv("PATRONI_WAL_KEEP_SIZE", "512MB").strip(),
        "wal_level": "replica",
        "wal_log_hints": "on",
    }
    archive_mode = os.getenv("PATRONI_ARCHIVE_MODE", "off").strip().lower()
    if archive_mode not in {"on", "off"}:
        raise ValueError("PATRONI_ARCHIVE_MODE must be on or off")
    postgres_parameters["archive_mode"] = archive_mode
    if archive_mode == "on":
        postgres_parameters["archive_timeout"] = seconds(
            "PATRONI_ARCHIVE_TIMEOUT", 300, minimum=1
        )
        postgres_parameters["archive_command"] = required("PATRONI_ARCHIVE_COMMAND")

    reviewed_pg_hba = [
        "local all all trust",
        "host all all 127.0.0.1/32 scram-sha-256",
        "host all all 172.16.0.0/12 scram-sha-256",
        f"host replication {replication_user} 172.16.0.0/12 scram-sha-256",
        f"host replication {replication_user} 10.77.0.0/24 scram-sha-256",
        "host all all 10.77.0.0/24 scram-sha-256",
    ]

    watchdog_mode = os.getenv("PATRONI_WATCHDOG_MODE", "off").strip().lower()
    if watchdog_mode not in {"off", "automatic", "required"}:
        raise ValueError("PATRONI_WATCHDOG_MODE must be off, automatic, or required")

    return {
        "scope": scope,
        "namespace": os.getenv("PATRONI_NAMESPACE", "/mvn/").strip() or "/mvn/",
        "name": name,
        "restapi": {
            "listen": "0.0.0.0:8008",
            "connect_address": rest_connect_address,
        },
        "etcd3": etcd3,
        "bootstrap": {
            "dcs": {
                "ttl": ttl,
                "loop_wait": loop_wait,
                "retry_timeout": retry_timeout,
                "maximum_lag_on_failover": integer(
                    "PATRONI_MAXIMUM_LAG_ON_FAILOVER", 1_048_576, minimum=0
                ),
                "check_timeline": True,
                "failsafe_mode": boolean("PATRONI_FAILSAFE_MODE", True),
                "synchronous_mode": boolean("PATRONI_SYNCHRONOUS_MODE", True),
                "synchronous_mode_strict": boolean("PATRONI_SYNCHRONOUS_MODE_STRICT", False),
                "synchronous_node_count": 1,
                "postgresql": {
                    "use_pg_rewind": True,
                    "use_slots": True,
                    "parameters": postgres_parameters,
                },
            },
            "initdb": [{"encoding": "UTF8"}, "data-checksums"],
            "pg_hba": list(reviewed_pg_hba),
        },
        "postgresql": {
            "listen": "0.0.0.0:5432",
            "connect_address": connect_address,
            "data_dir": data_dir,
            "bin_dir": "/usr/local/bin",
            "pgpass": pgpass,
            "authentication": {
                "replication": {
                    "username": replication_user,
                    "password": replication_password,
                },
                "superuser": {
                    "username": superuser,
                    "password": superuser_password,
                },
            },
            "parameters": {"password_encryption": "scram-sha-256"},
            # ``bootstrap.pg_hba`` only seeds a newly initialized database
            # cluster.  Keep the same reviewed rules in local Patroni config
            # so existing clusters converge too, including replication from
            # Docker's 172.16.0.0/12 bridge used by the isolated backup helper.
            "pg_hba": list(reviewed_pg_hba),
        },
        "watchdog": {
            "mode": watchdog_mode,
            "device": os.getenv("PATRONI_WATCHDOG_DEVICE", "/dev/watchdog").strip(),
            "safety_margin": integer("PATRONI_WATCHDOG_SAFETY_MARGIN", 5, minimum=-1),
        },
        "tags": {
            "nofailover": boolean("PATRONI_TAG_NOFAILOVER", False),
            "noloadbalance": boolean("PATRONI_TAG_NOLOADBALANCE", False),
            "clonefrom": boolean("PATRONI_TAG_CLONEFROM", False),
            "nosync": boolean("PATRONI_TAG_NOSYNC", False),
        },
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: render-patroni-config OUTPUT", file=sys.stderr)
        return 2
    try:
        config = render_config()
    except ValueError as exc:
        print(f"patroni_config_status=failed reason={exc}", file=sys.stderr)
        return 1
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(f"patroni_config_status=rendered path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
