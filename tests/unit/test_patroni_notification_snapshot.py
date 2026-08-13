from types import SimpleNamespace

from scripts.ha.patroni_notification_snapshot import (
    build_notification_snapshot,
    failure_snapshot,
)


def _build(*, failures=None, primary_code=200, lag=0):
    config = SimpleNamespace(ready_url="http://127.0.0.1:18080/api/ready")
    report = SimpleNamespace(failures=failures or [])
    primary = SimpleNamespace(patroni_name="zakup")
    standby = SimpleNamespace(patroni_name="mvn-api")

    def cluster_loader(_runner, _node, _path):
        return {
            "members": [
                {
                    "name": "zakup",
                    "role": "leader",
                    "state": "running",
                    "timeline": 20,
                },
                {
                    "name": "mvn-api",
                    "role": "sync_standby",
                    "state": "streaming",
                    "timeline": 20,
                    "lag": lag,
                },
            ]
        }

    def ready_loader(_runner, node, _url):
        if node is primary:
            return primary_code, {
                "api": "ready" if primary_code == 200 else "not_ready",
                "traffic": "enabled" if primary_code == 200 else "disabled",
            }
        return 503, {"api": "not_ready", "traffic": "disabled"}

    return build_notification_snapshot(
        config,
        object(),
        report,
        primary,
        standby,
        cluster_loader=cluster_loader,
        ready_loader=ready_loader,
    )


def test_snapshot_distinguishes_healthy_degraded_and_critical():
    healthy = _build()
    degraded = _build(failures=["replay lag exceeds limit"], lag=2_000_000)
    critical = _build(primary_code=503)

    assert healthy["status"] == "healthy"
    assert healthy["lag_bytes"] == 0
    assert healthy["standby_fenced"] is True
    assert degraded["status"] == "degraded"
    assert degraded["lag_bytes"] == 2_000_000
    assert critical["status"] == "critical"
    assert critical["primary_ready"] is False


def test_failure_snapshot_does_not_call_transport_failure_a_database_outage():
    transport = failure_snapshot(RuntimeError("reserve: Connection closed by host port 22"))
    split_brain = failure_snapshot(
        ValueError("unsafe Patroni topology: primary count=2 standby count=0")
    )

    assert transport["status"] == "monitoring_error"
    assert transport["failures"] == []
    assert split_brain["status"] == "critical"
    assert split_brain["failures"]
