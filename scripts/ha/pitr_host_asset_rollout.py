#!/usr/bin/env python3
"""Fail-closed rollout of the reviewed PITR host-asset release."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

try:
    from scripts.ha.pitr_cluster_topology import (
        ClusterTopology,
        discover_cluster_topology,
    )
    from scripts.ha.pitr_pinned_ssh import PatroniNode, PinnedSshContext
    from scripts.ha.pitr_remote_execution import (
        prepare_host_release_bundles,
        run_remote_maintenance_phase,
        run_remote_release_action,
    )
    from scripts.ha.pitr_target_compose import validate_target_compose_bundles
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_cluster_topology import (  # type: ignore[no-redef]
        ClusterTopology,
        discover_cluster_topology,
    )
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PatroniNode,
        PinnedSshContext,
    )
    from pitr_remote_execution import (  # type: ignore[no-redef]
        prepare_host_release_bundles,
        run_remote_maintenance_phase,
        run_remote_release_action,
    )
    from pitr_target_compose import (  # type: ignore[no-redef]
        validate_target_compose_bundles,
    )


Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]
TopologyDiscoverer = Callable[..., ClusterTopology]
ReleaseBundleBuilder = Callable[[Sequence[PatroniNode]], dict[str, str]]
ReleaseAction = Callable[..., str]
VerifyAction = Callable[..., None]
TargetComposeValidator = Callable[[Sequence[PatroniNode], Mapping[str, str]], str]

TRANSACTION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
RELEASE_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_BOOTSTRAP_HELPER = "/usr/local/sbin/mvn-postgres-pitr-bootstrap"
SUPPORTED_INSPECT_STATES = {
    "fresh",
    "matching-active",
    "matching-finalized",
}
RESUMABLE_INSPECT_STATES = {
    "matching-active",
    "matching-finalized",
}


@dataclass(frozen=True)
class HostAssetRolloutResult:
    transaction_id: str
    primary_alias: str
    standby_alias: str
    system_identifier: str
    timeline: int
    compose_profile: str
    release_digests: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class HostAssetRolloutDependencies:
    discover: TopologyDiscoverer = discover_cluster_topology
    bundles: ReleaseBundleBuilder = prepare_host_release_bundles
    release: ReleaseAction = run_remote_release_action
    verify: VerifyAction = run_remote_maintenance_phase
    target_compose: TargetComposeValidator = validate_target_compose_bundles


def validate_transaction_id(transaction_id: str) -> str:
    if not TRANSACTION_ID_RE.fullmatch(transaction_id):
        raise RuntimeError(
            "PITR host-asset transaction ID must be 32 lowercase hexadecimal "
            "characters"
        )
    return transaction_id


def _release_digest(rendered_bundle: str) -> str:
    try:
        bundle = json.loads(rendered_bundle)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("pinned PITR release bundle is invalid") from exc
    digest = bundle.get("release_sha256") if isinstance(bundle, dict) else None
    if not isinstance(digest, str) or not RELEASE_DIGEST_RE.fullmatch(digest):
        raise RuntimeError("pinned PITR release digest is invalid")
    return digest


class _HostAssetRollout:
    def __init__(
        self,
        *,
        context: PinnedSshContext,
        transaction_id: str,
        runner: Runner,
        dependencies: HostAssetRolloutDependencies,
        bootstrap_helper: str,
    ) -> None:
        if bootstrap_helper != DEFAULT_BOOTSTRAP_HELPER:
            raise RuntimeError("unexpected bootstrap helper path")
        self.context = context
        self.transaction_id = validate_transaction_id(transaction_id)
        self.runner = runner
        self.dependencies = dependencies
        self.bootstrap_helper = bootstrap_helper
        self.baseline: ClusterTopology | None = None
        self.roll_forward = False

    def _discover(self) -> ClusterTopology:
        return self.dependencies.discover(
            context=self.context,
            runner=self.runner,
        )

    def _guard_topology(self, *, stage: str) -> ClusterTopology:
        current = self._discover()
        baseline = self.baseline
        if baseline is None:
            self.baseline = current
            return current
        drift: list[str] = []
        if current.system_identifier != baseline.system_identifier:
            drift.append("system_identifier")
        if current.timeline != baseline.timeline:
            drift.append("timeline")
        if current.primary.alias != baseline.primary.alias:
            drift.append("primary")
        if current.standby.alias != baseline.standby.alias:
            drift.append("standby")
        if drift:
            raise RuntimeError(
                f"topology drift at {stage}: " + ", ".join(drift)
            )
        return current

    def _operate(
        self,
        *,
        stage: str,
        action: Callable[[], object],
        mutating: bool = False,
    ) -> object:
        self._guard_topology(stage=f"before {stage}")
        if mutating:
            # A lost SSH response cannot prove that the remote executor made no
            # durable progress. Every later failure must therefore be resumed
            # with this exact transaction ID instead of rolling back blindly.
            self.roll_forward = True
        action_error: BaseException | None = None
        result: object | None = None
        try:
            result = action()
        except BaseException as exc:
            action_error = exc
        try:
            self._guard_topology(stage=f"after {stage}")
        except BaseException as topology_error:
            if action_error is not None:
                raise RuntimeError(
                    f"{stage} failed: {action_error}; topology proof after the "
                    f"attempted operation also failed: {topology_error}"
                ) from topology_error
            raise
        if action_error is not None:
            raise action_error
        return result

    def _release(
        self,
        *,
        action: str,
        node: PatroniNode,
        release_bundle: str | None = None,
    ) -> str:
        return self.dependencies.release(
            node=node,
            context=self.context,
            action=action,
            txid=self.transaction_id,
            release_bundle=release_bundle,
            runner=self.runner,
        )

    def _verify(self, node: PatroniNode) -> None:
        self.dependencies.verify(
            node=node,
            context=self.context,
            bootstrap_helper=self.bootstrap_helper,
            phase="verify",
            transaction_id=self.transaction_id,
            runner=self.runner,
        )

    def _result(
        self,
        *,
        baseline: ClusterTopology,
        profile: str,
        bundles: Mapping[str, str],
        ordered_nodes: Sequence[PatroniNode],
    ) -> HostAssetRolloutResult:
        return HostAssetRolloutResult(
            transaction_id=self.transaction_id,
            primary_alias=baseline.primary.alias,
            standby_alias=baseline.standby.alias,
            system_identifier=baseline.system_identifier,
            timeline=baseline.timeline,
            compose_profile=profile,
            release_digests=tuple(
                (node.alias, _release_digest(bundles[node.project_dir]))
                for node in ordered_nodes
            ),
        )

    def run(self) -> HostAssetRolloutResult:
        baseline = self._guard_topology(stage="baseline")
        ordered_nodes = (baseline.standby, baseline.primary)
        bundles = self.dependencies.bundles(ordered_nodes)
        expected_projects = {node.project_dir for node in ordered_nodes}
        if set(bundles) != expected_projects:
            raise RuntimeError(
                "pinned PITR release bundle set does not match cluster nodes"
            )
        profile = self.dependencies.target_compose(ordered_nodes, bundles)

        compatibility: dict[str, str] = {}
        for node in ordered_nodes:
            state = self._operate(
                stage=f"bundle compatibility {node.alias}",
                action=lambda node=node: self._release(
                    action="inspect",
                    node=node,
                    release_bundle=bundles[node.project_dir],
                ),
            )
            if not isinstance(state, str):
                raise RuntimeError("release compatibility returned a non-string state")
            compatibility[node.alias] = state

        unsupported = {
            state
            for state in compatibility.values()
            if state not in SUPPORTED_INSPECT_STATES
        }
        if unsupported:
            if "matching-rolled-back" in unsupported:
                raise RuntimeError(
                    "this PITR host-asset transaction was durably rolled back; "
                    "start a new workflow run with a new transaction ID"
                )
            if "preflight-fenced" in unsupported:
                raise RuntimeError(
                    "a full PITR migration preflight owns durable fenced state; "
                    "resume or clean up that reviewed migration instead"
                )
            raise RuntimeError(
                "release compatibility returned an unsupported state: "
                + ", ".join(sorted(unsupported))
            )

        if any(
            state in RESUMABLE_INSPECT_STATES
            for state in compatibility.values()
        ):
            self.roll_forward = True

        try:
            if all(
                state == "matching-finalized"
                for state in compatibility.values()
            ):
                self._operate(
                    stage=f"strict PITR verify {baseline.primary.alias}",
                    action=lambda: self._verify(baseline.primary),
                )
                return self._result(
                    baseline=baseline,
                    profile=profile,
                    bundles=bundles,
                    ordered_nodes=ordered_nodes,
                )

            # Resume/reopen any durable transaction generation before touching a
            # fresh peer. This keeps a retry moving toward one exact release.
            apply_nodes = tuple(
                sorted(
                    ordered_nodes,
                    key=lambda node: compatibility[node.alias] == "fresh",
                )
            )
            expected_apply_results = {
                "fresh": "applied",
                "matching-active": "resumed",
                "matching-finalized": "reopened",
            }
            for node in apply_nodes:
                state = compatibility[node.alias]
                result = self._operate(
                    stage=f"bundle apply {node.alias}",
                    action=lambda node=node: self._release(
                        action="apply",
                        node=node,
                        release_bundle=bundles[node.project_dir],
                    ),
                    mutating=True,
                )
                expected_result = expected_apply_results[state]
                if result != expected_result:
                    raise RuntimeError(
                        f"bundle apply {node.alias} returned {result!r}; "
                        f"expected {expected_result!r}"
                    )

            # Finalize standby first. If the second finalize is interrupted, an
            # exact same-transaction replay reopens the finalized peer and
            # resumes the active peer before finalizing both again.
            for node in ordered_nodes:
                result = self._operate(
                    stage=f"bundle finalize {node.alias}",
                    action=lambda node=node: self._release(
                        action="finalize",
                        node=node,
                    ),
                    mutating=True,
                )
                if result not in {"finalized", "already-finalized"}:
                    raise RuntimeError(
                        f"bundle finalize {node.alias} returned {result!r}"
                    )

            for node in ordered_nodes:
                state = self._operate(
                    stage=f"finalized bundle proof {node.alias}",
                    action=lambda node=node: self._release(
                        action="inspect",
                        node=node,
                        release_bundle=bundles[node.project_dir],
                    ),
                )
                if state != "matching-finalized":
                    raise RuntimeError(
                        f"{node.alias} did not retain the finalized PITR release"
                    )

            self._operate(
                stage=f"strict PITR verify {baseline.primary.alias}",
                action=lambda: self._verify(baseline.primary),
            )
        except BaseException as exc:
            if self.roll_forward:
                raise RuntimeError(
                    "PITR host-asset rollout entered roll-forward state; do not "
                    "copy files or delete manifests manually; rerun with the "
                    f"same transaction ID {self.transaction_id}: {exc}"
                ) from exc
            raise

        return self._result(
            baseline=baseline,
            profile=profile,
            bundles=bundles,
            ordered_nodes=ordered_nodes,
        )


def rollout_host_assets(
    *,
    context: PinnedSshContext,
    transaction_id: str,
    runner: Runner,
    dependencies: HostAssetRolloutDependencies | None = None,
    bootstrap_helper: str = DEFAULT_BOOTSTRAP_HELPER,
) -> HostAssetRolloutResult:
    """Install and attest one exact PITR host release on both Patroni nodes."""

    return _HostAssetRollout(
        context=context,
        transaction_id=transaction_id,
        runner=runner,
        dependencies=dependencies or HostAssetRolloutDependencies(),
        bootstrap_helper=bootstrap_helper,
    ).run()
