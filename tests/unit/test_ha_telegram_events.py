import json

from scripts.ha.ha_telegram_events import decide, main


def _snapshot(
    status: str = "healthy",
    *,
    primary: str = "mvn-api",
    standby: str = "zakup",
    lag_bytes: int | None = 0,
    failures: list[str] | None = None,
    detail: str = "",
):
    return {
        "status": status,
        "observed_at": "2026-08-14T00:00:00+00:00",
        "primary": primary,
        "standby": standby,
        "timeline": 20,
        "lag_bytes": lag_bytes,
        "primary_ready": status != "critical",
        "standby_fenced": True,
        "replication_state": "streaming",
        "sync_state": "sync_standby",
        "failures": failures or [],
        "detail": detail,
    }


def _baseline(snapshot=None):
    first = decide(None, snapshot or _snapshot())
    assert first.kind is None
    return first.state


def test_primary_change_is_immediate_and_names_both_locations():
    previous = _baseline()

    decision = decide(
        previous,
        _snapshot(primary="zakup", standby="mvn-api"),
    )

    assert decision.kind == "primary_changed"
    assert "Было: 🇳🇱 Нидерланды — mvn-api" in decision.message
    assert "Стало: 🇧🇾 Беларусь — zakup" in decision.message
    assert "Причина переключения пока не подтверждена" in decision.message
    assert "отставание WAL 0 байт" in decision.message


def test_degraded_and_recovered_events_are_deduplicated():
    previous = _baseline()
    degraded = _snapshot(
        "degraded",
        failures=["reserve: Patroni /sync endpoint is not healthy"],
    )

    opened = decide(previous, degraded)
    repeated = decide(opened.state, degraded)
    recovered = decide(repeated.state, _snapshot())

    assert opened.kind == "degraded"
    assert "без полноценного резерва" in opened.message
    assert repeated.kind is None
    assert recovered.kind == "recovered"
    assert "Резервирование PostgreSQL восстановлено" in recovered.message


def test_first_confirmed_problem_is_not_silenced_without_previous_state():
    degraded = decide(
        None,
        _snapshot(
            "degraded",
            failures=["reserve: Patroni /sync endpoint is not healthy"],
        ),
    )
    critical = decide(
        None,
        _snapshot(
            "critical",
            primary="",
            standby="",
            lag_bytes=None,
            failures=["unsafe Patroni topology: primary count=2 standby count=0"],
        ),
    )

    assert degraded.kind == "degraded"
    assert "синхронная реплика" in degraded.message
    assert "/sync endpoint" not in degraded.message
    assert critical.kind == "critical"
    assert "единственный безопасный primary" in critical.message
    assert "primary count=" not in critical.message


def test_monitoring_error_alerts_only_after_two_failures_then_recovers():
    previous = _baseline()
    unavailable = _snapshot(
        "monitoring_error",
        primary="",
        standby="",
        lag_bytes=None,
        detail="reserve: Connection closed by host port 22",
    )

    first = decide(previous, unavailable)
    second = decide(first.state, unavailable)
    repeated = decide(second.state, unavailable)
    recovered = decide(repeated.state, _snapshot())

    assert first.kind is None
    assert second.kind == "monitoring_error"
    assert "Это не означает, что PostgreSQL остановлен" in second.message
    assert "Primary: 🇳🇱 Нидерланды — mvn-api" in second.message
    assert "нет ответа от 🇧🇾 Беларусь — zakup" in second.message
    assert "Connection closed" not in second.message
    assert repeated.kind is None
    assert recovered.kind == "monitoring_recovered"
    assert "ошибка была связана с проверкой соединения" in recovered.message


def test_critical_topology_alert_is_immediate():
    previous = _baseline()

    decision = decide(
        previous,
        _snapshot(
            "critical",
            primary="",
            standby="",
            lag_bytes=None,
            failures=["unsafe Patroni topology: primary count=2 standby count=0"],
        ),
    )

    assert decision.kind == "critical"
    assert "Критическая проблема PostgreSQL HA" in decision.message
    assert "Автоматически роли не меняйте" in decision.message


def test_cli_uses_connection_log_as_monitoring_fallback(tmp_path):
    previous_path = tmp_path / "previous.json"
    previous_path.write_text(json.dumps(_baseline()), encoding="utf-8")
    log_path = tmp_path / "check.log"
    log_path.write_text(
        "[patroni-maintenance][error] reserve: Connection closed by host port 22\n",
        encoding="utf-8",
    )
    state_path = tmp_path / "state.json"
    message_path = tmp_path / "message.txt"
    output_path = tmp_path / "github-output.txt"

    assert (
        main(
            [
                "--snapshot",
                str(tmp_path / "missing-snapshot.json"),
                "--previous-state",
                str(previous_path),
                "--fallback-log",
                str(log_path),
                "--state-output",
                str(state_path),
                "--message-output",
                str(message_path),
                "--github-output",
                str(output_path),
            ]
        )
        == 0
    )
    assert json.loads(state_path.read_text())["monitoring_error_streak"] == 1
    assert message_path.read_text() == ""
    assert "notify=false" in output_path.read_text()
