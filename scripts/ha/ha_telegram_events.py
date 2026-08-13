#!/usr/bin/env python3
"""Turn Patroni observations into deduplicated, owner-readable Telegram events."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


STATE_VERSION = 1
SNAPSHOT_STATES = {"healthy", "degraded", "critical", "monitoring_error"}
NODE_LABELS = {
    "mvn-api": "🇳🇱 Нидерланды — mvn-api",
    "zakup": "🇧🇾 Беларусь — zakup",
}


@dataclass(frozen=True)
class Decision:
    kind: str | None
    message: str
    state: dict[str, Any]


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root in {path} must be an object")
    return value


def _snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    status = str(value.get("status") or "").strip()
    if status not in SNAPSHOT_STATES:
        raise ValueError(f"unsupported HA snapshot status: {status or '<empty>'}")
    failures = value.get("failures") or []
    if not isinstance(failures, list) or not all(isinstance(item, str) for item in failures):
        raise ValueError("HA snapshot failures must be a string list")
    return {
        "status": status,
        "observed_at": str(value.get("observed_at") or "").strip(),
        "primary": str(value.get("primary") or "").strip(),
        "standby": str(value.get("standby") or "").strip(),
        "timeline": value.get("timeline"),
        "lag_bytes": value.get("lag_bytes"),
        "primary_ready": value.get("primary_ready"),
        "standby_fenced": value.get("standby_fenced"),
        "replication_state": str(value.get("replication_state") or "").strip(),
        "sync_state": str(value.get("sync_state") or "").strip(),
        "failures": failures[:6],
        "detail": str(value.get("detail") or "").strip()[:500],
    }


def _state(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value or value.get("version") != STATE_VERSION:
        return {
            "version": STATE_VERSION,
            "last_confirmed": None,
            "last_observation": None,
            "monitoring_error_streak": 0,
            "monitoring_alert_open": False,
        }
    confirmed = value.get("last_confirmed")
    observation = value.get("last_observation")
    return {
        "version": STATE_VERSION,
        "last_confirmed": _snapshot(confirmed) if isinstance(confirmed, Mapping) else None,
        "last_observation": _snapshot(observation) if isinstance(observation, Mapping) else None,
        "monitoring_error_streak": max(0, int(value.get("monitoring_error_streak") or 0)),
        "monitoring_alert_open": bool(value.get("monitoring_alert_open", False)),
    }


def _node(alias: str) -> str:
    return NODE_LABELS.get(alias, alias or "не определён")


def _service_line(snapshot: Mapping[str, Any]) -> str:
    if snapshot.get("primary_ready") is True:
        return "Сайт и API: работают"
    return "Сайт и API: требуют проверки"


def _replication_line(snapshot: Mapping[str, Any]) -> str:
    lag = snapshot.get("lag_bytes")
    if snapshot.get("status") == "healthy":
        lag_bytes = lag if isinstance(lag, int) else 0
        return f"Репликация: синхронная, отставание WAL {lag_bytes} байт"
    if isinstance(lag, int):
        return f"WAL lag: {lag} байт"
    return "Репликация: резервный узел не подтверждён"


def _humanize_problem(problem: str) -> str:
    lowered = problem.lower()
    mappings = (
        (
            ("unsafe patroni topology", "primary count="),
            "не подтверждён единственный безопасный primary",
        ),
        (
            ("/sync endpoint", "sync_state="),
            "резервный сервер не подтверждён как синхронная реплика",
        ),
        (
            ("replica lag", "replay lag", "wal receiver lag"),
            "реплика отстаёт по журналу изменений",
        ),
        (
            ("not writable primary",),
            "основной сервер не подтверждён как доступный для записи",
        ),
        (
            ("not in recovery",),
            "резервный сервер не подтверждён в безопасном режиме standby",
        ),
        (
            ("replication state=", "wal receiver status="),
            "репликация не находится в рабочем состоянии streaming",
        ),
        (
            ("no replication slot", "replication slot"),
            "не подтверждён защищающий репликацию WAL-слот",
        ),
        (
            ("pending_restart",),
            "один из серверов ожидает обязательного перезапуска PostgreSQL",
        ),
        (
            ("members disagree on timeline", "timeline mismatch"),
            "серверы расходятся по истории WAL",
        ),
        (
            ("system identifier",),
            "серверы сообщили разные идентификаторы кластера PostgreSQL",
        ),
        (
            ("etcd quorum",),
            "не подтверждён кворум координаторов автоматического переключения",
        ),
        (
            ("readiness", "no api app service"),
            "служебная проверка API не подтвердила безопасную готовность серверов",
        ),
        (
            ("role agent", "scheduler_runtime"),
            "служба автоматического назначения ролей работает некорректно",
        ),
        (
            ("failsafe mode", "cluster is paused", "no leader lock"),
            "Patroni не подтвердил безопасное автоматическое управление кластером",
        ),
    )
    for markers, message in mappings:
        if any(marker in lowered for marker in markers):
            return message
    return "одна из проверок безопасной репликации не прошла"


def _humanize_monitoring_error(detail: str) -> str:
    lowered = detail.lower()
    location = "HA-серверами"
    if lowered.startswith("api:"):
        location = NODE_LABELS["mvn-api"]
    elif lowered.startswith("reserve:"):
        location = NODE_LABELS["zakup"]
    if any(
        marker in lowered
        for marker in (
            "connection closed",
            "connection refused",
            "no route to host",
            "operation timed out",
            "timed out",
            "timeout",
        )
    ):
        return f"нет ответа от {location} по служебному каналу"
    if "invalid patroni json" in lowered or "unexpected patroni payload" in lowered:
        return f"ответ от {location} получен, но состояние Patroni не удалось прочитать"
    if "is required" in lowered:
        return "проверка запущена с неполной служебной конфигурацией"
    return "служебная проверка не смогла получить состояние HA-серверов"


def _switch_message(previous: Mapping[str, Any], current: Mapping[str, Any]) -> str:
    lines = [
        "🟠 PostgreSQL: переключение primary",
        "",
        f"Было: {_node(str(previous.get('primary') or ''))}",
        f"Стало: {_node(str(current.get('primary') or ''))}",
        "",
        _service_line(current),
        _replication_line(current),
    ]
    if current.get("status") == "healthy":
        lines.extend(["", "Кластер снова защищён синхронной репликой."])
    else:
        lines.extend(
            [
                "",
                "Новый primary работает, но полноценное резервирование "
                "ещё не подтверждено.",
            ]
        )
    lines.extend(
        [
            "Причина переключения пока не подтверждена.",
            "Действия от вас сейчас не требуются.",
        ]
    )
    return "\n".join(lines)


def _degraded_message(current: Mapping[str, Any]) -> str:
    failure = next(iter(current.get("failures") or []), "standby не прошёл проверку")
    return "\n".join(
        [
            "🟠 PostgreSQL работает без полноценного резерва",
            "",
            f"Primary: {_node(str(current.get('primary') or ''))}",
            f"Standby: {_node(str(current.get('standby') or ''))}",
            _service_line(current),
            _replication_line(current),
            "",
            f"Что обнаружено: {_humanize_problem(failure)}.",
            "Запись данных продолжается, но отказоустойчивость снижена.",
        ]
    )


def _critical_message(current: Mapping[str, Any]) -> str:
    failure = next(
        iter(current.get("failures") or []),
        current.get("detail") or "primary не подтверждён",
    )
    return "\n".join(
        [
            "🔴 Критическая проблема PostgreSQL HA",
            "",
            _service_line(current),
            f"Primary: {_node(str(current.get('primary') or ''))}",
            f"Что обнаружено: {_humanize_problem(str(failure))}.",
            "",
            "Требуется срочная техническая проверка. Автоматически роли не меняйте.",
        ]
    )


def _recovered_message(current: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "🟢 Резервирование PostgreSQL восстановлено",
            "",
            f"Primary: {_node(str(current.get('primary') or ''))}",
            f"Standby: {_node(str(current.get('standby') or ''))}",
            _service_line(current),
            _replication_line(current),
            "",
            "Кластер снова защищён от отказа одного сервера.",
        ]
    )


def _monitoring_error_message(
    last_confirmed: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> str:
    detail = current.get("detail") or next(
        iter(current.get("failures") or []),
        "неизвестная ошибка соединения",
    )
    lines = [
        "🟡 Не удалось проверить HA-серверы",
        "",
        "Две проверки подряд не смогли подтвердить состояние кластера.",
        "Это не означает, что PostgreSQL остановлен.",
    ]
    if last_confirmed:
        lines.extend(
            [
                "",
                "Последняя подтверждённая топология:",
                f"Primary: {_node(str(last_confirmed.get('primary') or ''))}",
                f"Standby: {_node(str(last_confirmed.get('standby') or ''))}",
            ]
        )
    lines.extend(
        [
            "",
            f"Что произошло: {_humanize_monitoring_error(str(detail))}.",
            "Повторная проверка выполнится автоматически.",
        ]
    )
    return "\n".join(lines)


def _monitoring_recovered_message(current: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "🟢 Мониторинг HA снова работает",
            "",
            f"Primary: {_node(str(current.get('primary') or ''))}",
            f"Standby: {_node(str(current.get('standby') or ''))}",
            _service_line(current),
            _replication_line(current),
            "",
            "Предыдущая ошибка была связана с проверкой соединения, "
            "а не с подтверждённой остановкой PostgreSQL.",
        ]
    )


def decide(previous_raw: Mapping[str, Any] | None, current_raw: Mapping[str, Any]) -> Decision:
    previous = _state(previous_raw)
    current = _snapshot(current_raw)
    last_confirmed = previous["last_confirmed"]
    next_state = dict(previous)
    next_state["last_observation"] = current

    if current["status"] == "monitoring_error":
        streak = previous["monitoring_error_streak"] + 1
        next_state["monitoring_error_streak"] = streak
        if streak >= 2 and not previous["monitoring_alert_open"]:
            next_state["monitoring_alert_open"] = True
            return Decision(
                "monitoring_error",
                _monitoring_error_message(last_confirmed, current),
                next_state,
            )
        return Decision(None, "", next_state)

    next_state["monitoring_error_streak"] = 0
    monitoring_was_open = previous["monitoring_alert_open"]
    next_state["monitoring_alert_open"] = False
    next_state["last_confirmed"] = current

    if last_confirmed is None and current["status"] == "healthy":
        return Decision(None, "", next_state)
    if last_confirmed is None and current["status"] == "critical":
        return Decision("critical", _critical_message(current), next_state)
    if last_confirmed is None and current["status"] == "degraded":
        return Decision("degraded", _degraded_message(current), next_state)
    if current["primary"] and current["primary"] != last_confirmed["primary"]:
        return Decision("primary_changed", _switch_message(last_confirmed, current), next_state)
    if current["status"] == "critical" and last_confirmed["status"] != "critical":
        return Decision("critical", _critical_message(current), next_state)
    if current["status"] == "degraded" and last_confirmed["status"] == "healthy":
        return Decision("degraded", _degraded_message(current), next_state)
    if current["status"] == "healthy" and last_confirmed["status"] in {"degraded", "critical"}:
        return Decision("recovered", _recovered_message(current), next_state)
    if monitoring_was_open:
        return Decision("monitoring_recovered", _monitoring_recovered_message(current), next_state)
    return Decision(None, "", next_state)


def _fallback_snapshot(log_path: Path) -> dict[str, Any]:
    detail = "проверка завершилась до получения топологии"
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        lines = []
    for line in reversed(lines):
        lowered = line.lower()
        if any(
            marker in lowered
            for marker in (
                "connection closed",
                "timed out",
                "timeout",
                "connection refused",
            )
        ):
            detail = line.strip()[-300:]
            break
    return {
        "status": "monitoring_error",
        "observed_at": "",
        "failures": [],
        "detail": detail,
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _write_github_output(path: Path | None, *, notify: bool, kind: str | None) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as output:
        output.write(f"notify={'true' if notify else 'false'}\n")
        output.write(f"event_kind={kind or 'none'}\n")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--previous-state", type=Path, required=True)
    parser.add_argument("--fallback-log", type=Path, required=True)
    parser.add_argument("--state-output", type=Path, required=True)
    parser.add_argument("--message-output", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or os.sys.argv[1:])
    current = _load_object(args.snapshot) or _fallback_snapshot(args.fallback_log)
    previous = _load_object(args.previous_state)
    decision = decide(previous, current)
    _write_json(args.state_output, decision.state)
    args.message_output.write_text(decision.message, encoding="utf-8")
    _write_github_output(
        args.github_output
        or (
            Path(os.environ["GITHUB_OUTPUT"])
            if os.getenv("GITHUB_OUTPUT")
            else None
        ),
        notify=decision.kind is not None,
        kind=decision.kind,
    )
    print(
        f"ha_telegram_event status=classified event={decision.kind or 'none'} "
        f"snapshot={current.get('status', 'unknown')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
