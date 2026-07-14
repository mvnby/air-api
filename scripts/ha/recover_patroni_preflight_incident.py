#!/usr/bin/env python3
"""Close one exact preflight-only Patroni rollout incident without DB mutation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

try:
    from scripts.ha.patroni_preflight_incident_recovery import INCIDENT_CONTRACTS
    from scripts.ha.patroni_preflight_recovery_remote import run_remote_action
    from scripts.ha.patroni_rollout_local import default_runner, local_contract_digests
    from scripts.ha.pitr_cluster_topology import ClusterTopology, discover_cluster_topology
    from scripts.ha.pitr_pinned_ssh import (
        PATRONI_NODES,
        PinnedSshContext,
        create_context,
        validate_effective_config,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from patroni_preflight_incident_recovery import INCIDENT_CONTRACTS  # type: ignore[no-redef]
    from patroni_preflight_recovery_remote import run_remote_action  # type: ignore[no-redef]
    from patroni_rollout_local import (  # type: ignore[no-redef]
        default_runner,
        local_contract_digests,
    )
    from pitr_cluster_topology import (  # type: ignore[no-redef]
        ClusterTopology,
        discover_cluster_topology,
    )
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PATRONI_NODES,
        PinnedSshContext,
        create_context,
        validate_effective_config,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "deploy/ha/patroni/incidents/1053e46eb933ebaaffed042ac1b73170.json"
)
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")
TX_RE = re.compile(r"[0-9a-f]{32}")
IMAGE_RE = re.compile(
    r"ghcr[.]io/mvnby/air-api/patroni@sha256:[0-9a-f]{64}"
)
Runner = Callable[..., object]


@dataclass(frozen=True)
class RecoveryResult:
    current_image: str
    primary: str
    system_identifier: str
    timeline: int
    transaction_id: str


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"


def _safe_manifest(path: Path) -> Mapping[str, object]:
    if path.resolve() != DEFAULT_MANIFEST.resolve():
        raise RuntimeError("only the reviewed Patroni incident manifest is accepted")
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise RuntimeError("incident manifest metadata is unsafe")
    raw = path.read_bytes()
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("incident manifest is invalid JSON") from exc
    if not isinstance(manifest, Mapping) or _canonical(manifest) != raw:
        raise RuntimeError("incident manifest must be exact canonical JSON")
    _validate_manifest(manifest)
    return manifest


def _validate_manifest(manifest: Mapping[str, object]) -> None:
    required = {
        "baseline",
        "current_image",
        "incident_deploy_sha",
        "maintenance_transaction_id",
        "nodes",
        "publish_run_attempt",
        "publish_run_id",
        "rollout_controller_sha256",
        "target_image",
        "transaction_id",
        "version",
    }
    if set(manifest) != required or manifest.get("version") != 1:
        raise RuntimeError("incident manifest fields are not exact")
    if (
        not COMMIT_RE.fullmatch(str(manifest.get("incident_deploy_sha", "")))
        or not TX_RE.fullmatch(str(manifest.get("transaction_id", "")))
        or not TX_RE.fullmatch(str(manifest.get("maintenance_transaction_id", "")))
        or not DIGEST_RE.fullmatch(str(manifest.get("rollout_controller_sha256", "")))
        or not IMAGE_RE.fullmatch(str(manifest.get("current_image", "")))
        or not IMAGE_RE.fullmatch(str(manifest.get("target_image", "")))
        or manifest.get("current_image") == manifest.get("target_image")
    ):
        raise RuntimeError("incident manifest generation identity is invalid")
    if not isinstance(manifest.get("publish_run_id"), str) or not re.fullmatch(
        r"[1-9][0-9]{5,14}", str(manifest["publish_run_id"])
    ):
        raise RuntimeError("incident manifest publish run is invalid")
    if type(manifest.get("publish_run_attempt")) is not int or not (
        1 <= int(manifest["publish_run_attempt"]) <= 2_147_483_647
    ):
        raise RuntimeError("incident manifest publish attempt is invalid")
    baseline = manifest.get("baseline")
    if not isinstance(baseline, Mapping) or set(baseline) != {
        "primary",
        "system_identifier",
        "timeline",
    }:
        raise RuntimeError("incident manifest baseline is invalid")
    if (
        baseline.get("primary") not in {node.alias for node in PATRONI_NODES}
        or not re.fullmatch(r"[0-9]{10,24}", str(baseline.get("system_identifier", "")))
        or type(baseline.get("timeline")) is not int
        or int(baseline["timeline"]) < 1
    ):
        raise RuntimeError("incident manifest topology is invalid")
    nodes = manifest.get("nodes")
    if not isinstance(nodes, Mapping) or set(nodes) != {
        node.alias for node in PATRONI_NODES
    }:
        raise RuntimeError("incident manifest node set is invalid")
    node_fields = {
        "compose_contract_sha256",
        "compose_source_sha256",
        "journal_after_sha256",
        "journal_before_operation",
        "journal_before_sha256",
        "journal_compose_contract_sha256",
    }
    for node in PATRONI_NODES:
        contract = nodes.get(node.alias)
        if not isinstance(contract, Mapping) or set(contract) != node_fields:
            raise RuntimeError(f"incident manifest contract is invalid for {node.alias}")
        for key in node_fields - {"journal_before_operation"}:
            if not DIGEST_RE.fullmatch(str(contract.get(key, ""))):
                raise RuntimeError(f"incident manifest digest is invalid for {node.alias}")
        reviewed = INCIDENT_CONTRACTS[node.alias]
        if (
            contract.get("journal_before_sha256") != reviewed.before_sha256
            or contract.get("journal_after_sha256") != reviewed.after_sha256
            or contract.get("journal_before_operation") != reviewed.before_operation
        ):
            raise RuntimeError(f"incident transformer and manifest disagree for {node.alias}")
        if hashlib.sha256(node.compose_source.read_bytes()).hexdigest() != contract.get(
            "compose_source_sha256"
        ):
            raise RuntimeError(f"tracked Compose source differs for {node.alias}")


def _prove_topology(
    topology: ClusterTopology, manifest: Mapping[str, object]
) -> None:
    baseline = manifest["baseline"]
    assert isinstance(baseline, Mapping)
    if (
        topology.primary.alias != baseline["primary"]
        or topology.system_identifier != baseline["system_identifier"]
        or topology.timeline != baseline["timeline"]
    ):
        raise RuntimeError("live Patroni topology differs from the exact incident baseline")


def recover_patroni_preflight_incident(
    *,
    context: PinnedSshContext,
    recovery_deploy_sha: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    runner=default_runner,
    discover=discover_cluster_topology,
    remote=run_remote_action,
) -> RecoveryResult:
    if not COMMIT_RE.fullmatch(recovery_deploy_sha):
        raise RuntimeError("recovery deploy SHA is invalid")
    manifest = _safe_manifest(manifest_path)
    measured_contracts = local_contract_digests(recovery_deploy_sha)
    nodes = manifest["nodes"]
    assert isinstance(nodes, Mapping)
    expected_contracts = {
        alias: str(contract["compose_contract_sha256"])
        for alias, contract in nodes.items()
        if isinstance(contract, Mapping)
    }
    if measured_contracts != expected_contracts:
        raise RuntimeError("reviewed corrected Compose contracts do not match the incident")

    def topology() -> ClusterTopology:
        value = discover(context=context, runner=runner)
        _prove_topology(value, manifest)
        return value

    original = topology()
    statuses = {
        node.alias: remote(
            action="probe",
            manifest=manifest,
            node=node,
            context=context,
            recovery_deploy_sha=recovery_deploy_sha,
            runner=runner,
        )
        for node in PATRONI_NODES
    }
    if any(not status.get("marker_present") for status in statuses.values()) and not all(
        status.get("journal_state") == "after" and status.get("receipt_present") is True
        for status in statuses.values()
    ):
        raise RuntimeError("partial unfence exists before both incident journals are terminal")
    by_alias = {node.alias: node for node in PATRONI_NODES}
    for node in (original.standby, original.primary):
        status = statuses[node.alias]
        if status.get("journal_state") != "after" or status.get("receipt_present") is not True:
            remote(
                action="terminalize",
                manifest=manifest,
                node=node,
                context=context,
                recovery_deploy_sha=recovery_deploy_sha,
                runner=runner,
            )
    topology()
    terminal = {
        node.alias: remote(
            action="probe",
            manifest=manifest,
            node=node,
            context=context,
            recovery_deploy_sha=recovery_deploy_sha,
            runner=runner,
        )
        for node in PATRONI_NODES
    }
    if any(
        status.get("journal_state") != "after"
        or status.get("receipt_present") is not True
        for status in terminal.values()
    ):
        raise RuntimeError("both incident journals must be terminal before unfencing")
    for alias in (original.standby.alias, original.primary.alias):
        remote(
            action="unfence",
            manifest=manifest,
            node=by_alias[alias],
            context=context,
            recovery_deploy_sha=recovery_deploy_sha,
            runner=runner,
        )
    final = topology()
    final_statuses = {
        node.alias: remote(
            action="probe",
            manifest=manifest,
            node=node,
            context=context,
            recovery_deploy_sha=recovery_deploy_sha,
            runner=runner,
        )
        for node in PATRONI_NODES
    }
    if any(status.get("marker_present") is not False for status in final_statuses.values()):
        raise RuntimeError("incident cutover markers remain after exact recovery")
    return RecoveryResult(
        current_image=str(manifest["current_image"]),
        primary=final.primary.alias,
        system_identifier=final.system_identifier,
        timeline=final.timeline,
        transaction_id=str(manifest["transaction_id"]),
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deploy-sha", required=True)
    parser.add_argument("--identity-file", required=True, type=Path)
    parser.add_argument("--apply", required=True, choices=("true", "false"))
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if args.apply != "true":
        raise RuntimeError("incident recovery requires apply=true")
    with tempfile.TemporaryDirectory(prefix="mvn-patroni-recovery-ssh-") as raw:
        directory = Path(raw)
        directory.chmod(0o700)
        context = create_context(directory, args.identity_file)
        for node in PATRONI_NODES:
            validate_effective_config(node, context)
        result = recover_patroni_preflight_incident(
            context=context,
            recovery_deploy_sha=args.deploy_sha,
        )
    print(json.dumps(result.__dict__, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
