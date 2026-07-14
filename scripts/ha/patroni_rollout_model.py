"""Typed local contracts for the Patroni rollout orchestrator."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Sequence

try:
    from scripts.ha.pitr_cluster_topology import (
        ClusterTopology,
        discover_cluster_topology,
    )
    from scripts.ha.patroni_rollout_remote import read_status, run_remote_action
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_cluster_topology import (  # type: ignore[no-redef]
        ClusterTopology,
        discover_cluster_topology,
    )
    from patroni_rollout_remote import (  # type: ignore[no-redef]
        read_status,
        run_remote_action,
    )


Runner = Callable[[Sequence[str], str | None], object]
Discoverer = Callable[..., ClusterTopology]
RemoteAction = Callable[..., str]
StatusReader = Callable[..., dict[str, object]]
Sleeper = Callable[[float], None]


@dataclass(frozen=True)
class RolloutResult:
    transaction_id: str
    original_primary: str
    final_primary: str
    target_image: str
    system_identifier: str
    timeline: int


@dataclass(frozen=True)
class RolloutDependencies:
    discover: Discoverer = discover_cluster_topology
    remote: RemoteAction = run_remote_action
    status: StatusReader = read_status
    sleep: Sleeper = time.sleep
