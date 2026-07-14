"""Validated shared-journal state helpers for the Patroni rollout controller."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def completed_flags(
    statuses: Mapping[str, Mapping[str, object]],
    node_aliases: Sequence[str],
    operation: str,
) -> list[bool]:
    if set(statuses) != set(node_aliases):
        raise RuntimeError("remote rollout journals do not cover the exact node set")
    flags: list[bool] = []
    for alias in node_aliases:
        completed = statuses[alias].get("completed")
        if not isinstance(completed, list) or any(
            not isinstance(item, str) for item in completed
        ):
            raise RuntimeError("remote rollout journal completed list is invalid")
        flags.append(operation in completed)
    return flags


def record_flags(
    statuses: Mapping[str, Mapping[str, object]],
    node_aliases: Sequence[str],
    name: str,
) -> list[bool]:
    return completed_flags(statuses, node_aliases, "record:" + name)


def has_ambiguous_switchover_boundary(
    statuses: Mapping[str, Mapping[str, object]],
    node_aliases: Sequence[str],
) -> bool:
    if any(record_flags(statuses, node_aliases, "standby-updated")) or any(
        record_flags(statuses, node_aliases, "switched-over")
    ):
        return True
    completed = completed_flags(statuses, node_aliases, "switchover")
    return any(completed) or any(
        statuses[alias].get("operation") == "switchover" for alias in node_aliases
    )
