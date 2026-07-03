import os

import pytest

from scripts.ha.check_cloudflare_lb_config import (
    AuditConfig,
    AuditFailure,
    _format_cloudflare_http_error,
    audit_configuration,
    collect_credentials,
    load_env_file,
)


def _config() -> AuditConfig:
    return AuditConfig(
        hostname="api.mvn.by",
        primary_origin="185.250.45.54",
        standby_origin="193.47.42.213",
        host_header="api.mvn.by",
        monitor_path="/api/ready",
        monitor_method="GET",
        monitor_expected_code="200",
        require_adaptive_failover=True,
        require_session_affinity_off=True,
        allow_extra_default_pools=False,
    )


def _fixtures():
    load_balancers = [
        {
            "id": "lb-api",
            "name": "api.mvn.by",
            "enabled": True,
            "default_pools": ["pool-primary", "pool-standby"],
            "fallback_pool": "pool-primary",
            "adaptive_routing": {"failover_across_pools": True},
            "session_affinity": "none",
        }
    ]
    pools = [
        {
            "id": "pool-primary",
            "name": "mvn-api",
            "enabled": True,
            "monitor": "monitor-ready",
            "origins": [
                {
                    "name": "mvn-api",
                    "address": "185.250.45.54",
                    "enabled": True,
                    "header": {"Host": ["api.mvn.by"]},
                }
            ],
        },
        {
            "id": "pool-standby",
            "name": "zakup",
            "enabled": True,
            "monitor": "monitor-ready",
            "origins": [
                {
                    "name": "zakup",
                    "address": "193.47.42.213",
                    "enabled": True,
                    "header": {"Host": ["api.mvn.by"]},
                }
            ],
        },
    ]
    monitors = [
        {
            "id": "monitor-ready",
            "name": "mvn-api-ready",
            "type": "https",
            "method": "GET",
            "path": "/api/ready",
            "expected_codes": "200",
        }
    ]
    return load_balancers, pools, monitors


def test_audit_configuration_accepts_expected_active_passive_lb():
    load_balancers, pools, monitors = _fixtures()

    messages = audit_configuration(
        load_balancers=load_balancers,
        pools=pools,
        monitors=monitors,
        config=_config(),
    )

    assert "fallback_pool=primary(mvn-api)" in messages
    assert "primary_pool=mvn-api origin=185.250.45.54 monitor=ok" in messages
    assert "standby_pool=zakup origin=193.47.42.213 monitor=ok" in messages


def test_audit_configuration_rejects_standby_fallback_pool():
    load_balancers, pools, monitors = _fixtures()
    load_balancers[0]["fallback_pool"] = "pool-standby"

    with pytest.raises(AuditFailure, match="fallback_pool must be primary"):
        audit_configuration(
            load_balancers=load_balancers,
            pools=pools,
            monitors=monitors,
            config=_config(),
        )


def test_cloudflare_http_403_for_zone_lb_explains_required_token_permissions():
    message = _format_cloudflare_http_error(
        "/zones/zone-123/load_balancers",
        403,
        '{"success":false,"errors":[{"code":10000,"message":"Authentication error"}]}',
    )

    assert "10000: Authentication error" in message
    assert "Zone / Load Balancers / Read" in message
    assert "Account / Load Balancing: Monitors and Pools / Read" in message


def test_audit_configuration_rejects_reversed_pool_order():
    load_balancers, pools, monitors = _fixtures()
    load_balancers[0]["default_pools"] = ["pool-standby", "pool-primary"]

    with pytest.raises(AuditFailure, match="default_pools first two"):
        audit_configuration(
            load_balancers=load_balancers,
            pools=pools,
            monitors=monitors,
            config=_config(),
        )


def test_audit_configuration_rejects_missing_origin_host_header():
    load_balancers, pools, monitors = _fixtures()
    pools[1]["origins"][0]["header"] = {}

    with pytest.raises(AuditFailure, match="does not set Host header"):
        audit_configuration(
            load_balancers=load_balancers,
            pools=pools,
            monitors=monitors,
            config=_config(),
        )


def test_audit_configuration_rejects_monitor_path_drift():
    load_balancers, pools, monitors = _fixtures()
    monitors[0]["path"] = "/api/health"

    with pytest.raises(AuditFailure, match="path="):
        audit_configuration(
            load_balancers=load_balancers,
            pools=pools,
            monitors=monitors,
            config=_config(),
        )


def test_collect_credentials_prefers_lb_audit_token_over_generic_token():
    token, token_source, zone_id, account_id, missing = collect_credentials(
        {
            "CLOUDFLARE_API_TOKEN_LB_AUDIT": "audit-token",
            "CLOUDFLARE_LB_READ_TOKEN": "read-token",
            "CLOUDFLARE_API_TOKEN": "old-generic-token",
            "CLOUDFLARE_ZONE_ID": "zone",
            "CLOUDFLARE_ACCOUNT_ID": "account",
        }
    )

    assert token == "audit-token"
    assert token_source == "CLOUDFLARE_API_TOKEN_LB_AUDIT"
    assert zone_id == "zone"
    assert account_id == "account"
    assert missing == []


def test_collect_credentials_falls_back_to_github_read_token():
    token, token_source, _, _, missing = collect_credentials(
        {
            "CLOUDFLARE_LB_READ_TOKEN": "read-token",
            "CLOUDFLARE_API_TOKEN": "old-generic-token",
            "CLOUDFLARE_ZONE_ID": "zone",
            "CLOUDFLARE_ACCOUNT_ID": "account",
        }
    )

    assert token == "read-token"
    assert token_source == "CLOUDFLARE_LB_READ_TOKEN"
    assert missing == []


def test_collect_credentials_reports_all_accepted_token_names_when_token_missing():
    _, _, _, _, missing = collect_credentials(
        {
            "CLOUDFLARE_ZONE_ID": "zone",
            "CLOUDFLARE_ACCOUNT_ID": "account",
        }
    )

    assert missing == [
        "one of CLOUDFLARE_API_TOKEN_LB_AUDIT/CLOUDFLARE_LB_READ_TOKEN/CLOUDFLARE_API_TOKEN"
    ]


def test_load_env_file_reads_only_cloudflare_credentials_without_sourcing(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "CLOUDFLARE_API_TOKEN_LB_AUDIT=audit-token",
                "CLOUDFLARE_ZONE_ID=zone",
                "CLOUDFLARE_ACCOUNT_ID=account",
                "CLIENT_NAME=Дмитрий Иванов",
                "CACHE_HEADER=max-age=31536000, immutable",
            ]
        ),
        encoding="utf-8",
    )
    for name in (
        "CLOUDFLARE_API_TOKEN_LB_AUDIT",
        "CLOUDFLARE_ZONE_ID",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLIENT_NAME",
        "CACHE_HEADER",
    ):
        monkeypatch.delenv(name, raising=False)

    load_env_file(env_file)

    assert collect_credentials()[0] == "audit-token"
    assert "CLIENT_NAME" not in os.environ
    assert "CACHE_HEADER" not in os.environ
