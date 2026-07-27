#!/usr/bin/env python3
"""Fail-closed orchestration for the reviewed two-node PITR migration."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

try:
    from scripts.ha.pitr_communications_cutover import (
        run_remote_communications_cutover_preflight,
    )
    from scripts.ha.pitr_target_compose import validate_target_compose_bundles
    from scripts.ha.pitr_cluster_topology import (
        ClusterTopology,
        discover_cluster_topology,
    )
    from scripts.ha.pitr_pinned_ssh import (
        PatroniNode,
        PinnedSshContext,
        ssh_args,
    )
    from scripts.ha.pitr_remote_execution import (
        prepare_host_release_bundles,
        run_remote_fenced_provision_phase,
        run_remote_maintenance_phase,
        run_remote_release_action,
        run_remote_role_agent_phase,
        run_remote_secret_phase,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_communications_cutover import (  # type: ignore[no-redef]
        run_remote_communications_cutover_preflight,
    )
    from pitr_target_compose import (  # type: ignore[no-redef]
        validate_target_compose_bundles,
    )
    from pitr_cluster_topology import (  # type: ignore[no-redef]
        ClusterTopology,
        discover_cluster_topology,
    )
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PatroniNode,
        PinnedSshContext,
        ssh_args,
    )
    from pitr_remote_execution import (  # type: ignore[no-redef]
        prepare_host_release_bundles,
        run_remote_fenced_provision_phase,
        run_remote_maintenance_phase,
        run_remote_release_action,
        run_remote_role_agent_phase,
        run_remote_secret_phase,
    )


Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]
TopologyDiscoverer = Callable[..., ClusterTopology]
ReleaseAction = Callable[..., str]
ReleaseBundleBuilder = Callable[[Sequence[PatroniNode]], dict[str, str]]
SecretPhase = Callable[..., None]
MaintenancePhase = Callable[..., None]
FencedProvisionPhase = Callable[..., None]
RoleAgentPhase = Callable[..., None]
CommunicationsCutover = Callable[..., None]
TargetComposeValidator = Callable[..., str]

TRANSACTION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
DEFAULT_BOOTSTRAP_HELPER = "/usr/local/sbin/mvn-postgres-pitr-bootstrap"
RELEASE_COMPATIBILITY_STATES = {
    "fresh",
    "matching-active",
    "matching-finalized",
    "matching-rolled-back",
    "preflight-fenced",
}
ROLLBACK_RECOVERY_STATES = {
    "matching-active",
    "matching-rolled-back",
    "preflight-fenced",
}


@dataclass(frozen=True)
class MigrationResult:
    transaction_id: str
    primary_alias: str
    standby_alias: str
    system_identifier: str
    timeline: int


@dataclass(frozen=True)
class MigrationDependencies:
    discover: TopologyDiscoverer = discover_cluster_topology
    bundles: ReleaseBundleBuilder = prepare_host_release_bundles
    release: ReleaseAction = run_remote_release_action
    secret: SecretPhase = run_remote_secret_phase
    maintenance: MaintenancePhase = run_remote_maintenance_phase
    fenced_provision: FencedProvisionPhase = run_remote_fenced_provision_phase
    role_agent: RoleAgentPhase = run_remote_role_agent_phase
    communications_cutover: CommunicationsCutover = (
        run_remote_communications_cutover_preflight
    )
    target_compose: TargetComposeValidator = validate_target_compose_bundles


def validate_transaction_id(transaction_id: str) -> str:
    if not TRANSACTION_ID_RE.fullmatch(transaction_id):
        raise RuntimeError(
            "PITR transaction ID must be 32 lowercase hexadecimal characters"
        )
    return transaction_id


class _MigrationOrchestrator:
    def __init__(
        self,
        *,
        context: PinnedSshContext,
        env_text: str,
        transaction_id: str,
        runner: Runner,
        dependencies: MigrationDependencies,
        bootstrap_helper: str,
    ) -> None:
        if not isinstance(env_text, str) or not env_text:
            raise RuntimeError("PITR env payload must be one non-empty text value")
        if "\0" in env_text:
            raise RuntimeError("PITR env payload must not contain NUL bytes")
        if bootstrap_helper != DEFAULT_BOOTSTRAP_HELPER:
            raise RuntimeError("unexpected bootstrap helper path")
        self.context = context
        self.env_text = env_text
        self.transaction_id = validate_transaction_id(transaction_id)
        self.runner = runner
        self.dependencies = dependencies
        self.bootstrap_helper = bootstrap_helper
        self.baseline: ClusterTopology | None = None
        self.roll_forward = False
        self.owned_bundle_nodes: list[PatroniNode] = []
        self.release_bundles: dict[str, str] = {}
        self.role_agent_window_open = False

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

    def _mutate(
        self,
        *,
        stage: str,
        action: Callable[[], None],
        enter_roll_forward: bool = False,
    ) -> None:
        self._guard_topology(stage=f"before {stage}")
        if enter_roll_forward:
            self.roll_forward = True
        action_error: BaseException | None = None
        try:
            action()
        except BaseException as exc:  # Preserve proof after a possibly partial mutation.
            action_error = exc
        try:
            self._guard_topology(stage=f"after {stage}")
        except BaseException as topology_error:
            if action_error is not None:
                raise RuntimeError(
                    f"{stage} failed: {action_error}; topology proof after the "
                    f"attempted mutation also failed: {topology_error}"
                ) from topology_error
            raise
        if action_error is not None:
            raise action_error

    def _release(self, action: str, node: PatroniNode) -> str:
        try:
            result = self.dependencies.release(
                node=node,
                context=self.context,
                action=action,
                txid=self.transaction_id,
                release_bundle=(
                    self.release_bundles[node.project_dir]
                    if action in {"inspect", "apply"}
                    else None
                ),
                runner=self.runner,
            )
        except BaseException:
            if action == "apply":
                # A lost response or a rejected pre-existing journal does not
                # prove that this controller owns a rollback. Preserve every
                # durable journal and marker for an exact same-tx replay.
                self.roll_forward = True
            raise
        if action == "apply":
            if result == "applied":
                self.owned_bundle_nodes.append(node)
            elif result in {"resumed", "reopened"}:
                self.roll_forward = True
        return result

    def _secret(self, phase: str, node: PatroniNode) -> None:
        self.dependencies.secret(
            node=node,
            context=self.context,
            env_text=self.env_text,
            bootstrap_helper=self.bootstrap_helper,
            phase=phase,
            transaction_id=self.transaction_id,
            runner=self.runner,
        )

    def _maintenance(self, phase: str, node: PatroniNode) -> None:
        self.dependencies.maintenance(
            node=node,
            context=self.context,
            bootstrap_helper=self.bootstrap_helper,
            phase=phase,
            transaction_id=self.transaction_id,
            runner=self.runner,
        )

    def _fenced_provision(self, node: PatroniNode) -> None:
        self.dependencies.fenced_provision(
            node=node,
            context=self.context,
            bootstrap_helper=self.bootstrap_helper,
            transaction_id=self.transaction_id,
            runner=self.runner,
        )

    def _role_agent(self, phase: str, node: PatroniNode) -> None:
        self.dependencies.role_agent(
            node=node,
            context=self.context,
            phase=phase,
            transaction_id=self.transaction_id,
            runner=self.runner,
        )

    def _communications_cutover(self, node: PatroniNode) -> None:
        self.dependencies.communications_cutover(
            node=node,
            context=self.context,
            transaction_id=self.transaction_id,
            runner=self.runner,
        )

    def _run_with_standby_agent_quiesced(
        self,
        *,
        node: PatroniNode,
        stage: str,
        action: Callable[[], None],
    ) -> None:
        baseline = self.baseline
        if baseline is None or node.alias != baseline.standby.alias:
            raise RuntimeError("standby role-agent window requires the baseline standby")
        self.role_agent_window_open = True
        self._mutate(
            stage=f"role-agent quiesce {node.alias} before {stage}",
            action=lambda: self._role_agent("quiesce-standby", node),
            enter_roll_forward=True,
        )
        self._mutate(stage=f"{stage} {node.alias}", action=action)
        self._mutate(
            stage=f"role-agent resume {node.alias} after {stage}",
            action=lambda: self._role_agent("resume-standby", node),
        )
        self.role_agent_window_open = False

    def _rollback_owned_bundles(self, original_error: BaseException) -> None:
        failures: list[str] = []
        for node in reversed(self.owned_bundle_nodes):
            try:
                self._mutate(
                    stage=f"bundle rollback {node.alias}",
                    action=lambda node=node: self._release("rollback", node),
                )
            except BaseException as exc:
                failures.append(f"{node.alias}: {exc}")
        if failures:
            raise RuntimeError(
                f"cluster migration failed before configuration: {original_error}; "
                "bundle rollback was incomplete: " + "; ".join(failures)
            ) from original_error

    def _recover_durable_rollback(
        self,
        ordered_nodes: Sequence[PatroniNode],
        compatibility: dict[str, str],
    ) -> None:
        states = set(compatibility.values())
        unexpected = states - RELEASE_COMPATIBILITY_STATES
        if unexpected:
            raise RuntimeError(
                "release compatibility returned an unsupported state: "
                + ", ".join(sorted(unexpected))
            )
        if "matching-rolled-back" not in states:
            return
        if "matching-finalized" in states:
            raise RuntimeError(
                "durable rollback conflicts with a finalized peer; automatic "
                "cleanup was not attempted"
            )
        try:
            for node in reversed(ordered_nodes):
                if compatibility[node.alias] not in ROLLBACK_RECOVERY_STATES:
                    continue
                self._mutate(
                    stage=f"durable rollback recovery {node.alias}",
                    action=lambda node=node: self._release("rollback", node),
                )
        except BaseException as exc:
            raise RuntimeError(
                "durable rollback recovery is incomplete; retry with the same "
                f"transaction ID {self.transaction_id}: {exc}"
            ) from exc
        raise RuntimeError(
            f"release transaction {self.transaction_id} was durably rolled back "
            "and recovery cleanup completed; start the next migration with a "
            "new transaction ID"
        )

    def _resume_role_agents_after_failure(
        self,
        baseline: ClusterTopology,
        original_error: BaseException,
    ) -> RuntimeError:
        fence_failures: list[str] = []
        # Fence the former primary first, then the peer. These local actions do
        # not trust the baseline role; each removes app, bot, and PITR owners
        # before the controller attempts to discover a fresh topology.
        for node in (baseline.primary, baseline.standby):
            try:
                self._role_agent("quiesce-fenced", node)
            except BaseException as exc:
                fence_failures.append(f"{node.alias}: {exc}")

        if fence_failures:
            return RuntimeError(
                "cluster migration entered roll-forward state; do not roll back; "
                f"resume with the same transaction ID {self.transaction_id}: "
                f"{original_error}; pinned recovery could not prove both runtime "
                "fences and therefore did not resume either node: "
                + "; ".join(fence_failures)
            )

        try:
            fresh = self._discover()
            recovery_nodes = (fresh.standby, fresh.primary)
            topology_detail = (
                f"fresh topology standby={fresh.standby.alias} "
                f"primary={fresh.primary.alias}"
            )
        except BaseException as exc:
            return RuntimeError(
                "cluster migration entered roll-forward state; do not roll back; "
                f"resume with the same transaction ID {self.transaction_id}: "
                f"{original_error}; both runtimes are fenced, but fresh topology "
                f"is unavailable and neither node was resumed: {exc}"
            )

        failures: list[str] = []
        for node in recovery_nodes:
            try:
                expected_role = (
                    "standby" if node.alias == fresh.standby.alias else "primary"
                )
                self._role_agent(f"resume-{expected_role}", node)
                proved = self._discover()
                if proved != fresh:
                    raise RuntimeError("fresh topology changed during role-agent recovery")
            except BaseException as exc:
                failures.append(f"{node.alias}: {exc}")
                break
        recovery_problems = [
            *(f"resume {failure}" for failure in failures),
        ]
        detail = (
            "; pinned role-agent safety recovery failed: "
            + "; ".join(recovery_problems)
            if recovery_problems
            else "; pinned role agents were safely fenced, freshly ordered, and restarted"
        )
        return RuntimeError(
            "cluster migration entered roll-forward state; do not roll back; "
            f"resume with the same transaction ID {self.transaction_id}: "
            f"{original_error}; {topology_detail}{detail}"
        )

    def run(self) -> MigrationResult:
        baseline = self._guard_topology(stage="baseline")
        ordered_nodes = (baseline.standby, baseline.primary)
        self.release_bundles = self.dependencies.bundles(ordered_nodes)
        if set(self.release_bundles) != {node.project_dir for node in ordered_nodes}:
            raise RuntimeError("pinned release bundle set does not match cluster nodes")
        self.dependencies.target_compose(ordered_nodes, self.release_bundles)
        compatibility: dict[str, str] = {}
        for node in ordered_nodes:
            self._mutate(
                stage=f"bundle compatibility {node.alias}",
                action=lambda node=node: compatibility.__setitem__(
                    node.alias, self._release("inspect", node)
                ),
            )
        self._recover_durable_rollback(ordered_nodes, compatibility)
        if any(state != "fresh" for state in compatibility.values()):
            self.roll_forward = True
        try:
            self._mutate(
                stage=f"communications cutover preflight {baseline.primary.alias}",
                action=lambda: self._communications_cutover(baseline.primary),
            )
        except BaseException as exc:
            # A lost SSH response may have durably written both fences and its
            # receipt. The exact transaction is the only safe retry identity.
            self.roll_forward = True
            raise RuntimeError(
                "communications cutover preflight may have changed durable "
                "state; resume with the same transaction ID "
                f"{self.transaction_id}: {exc}"
            ) from exc
        release_nodes = tuple(
            sorted(
                ordered_nodes,
                key=lambda node: compatibility[node.alias] == "fresh",
            )
        )
        try:
            for node in release_nodes:
                self._mutate(
                    stage=f"bundle apply {node.alias}",
                    action=lambda node=node: self._release("apply", node),
                )
            for node in ordered_nodes:
                preflight = lambda node=node: self._secret("preflight", node)
                if node.alias == baseline.standby.alias:
                    self._run_with_standby_agent_quiesced(
                        node=node,
                        stage="preflight",
                        action=preflight,
                    )
                else:
                    self._mutate(
                        stage=f"preflight {node.alias}",
                        action=preflight,
                    )
            for node in ordered_nodes:
                # Provision each node inside its own minimal role-agent window.
                # The standby is already traffic-fenced. The current primary
                # is explicitly fenced before its agent is stopped, accepting
                # a short write outage rather than an unfenced former primary.
                quiesce_phase = (
                    "quiesce-standby"
                    if node.alias == baseline.standby.alias
                    else "quiesce-fenced"
                )
                if node.alias == baseline.primary.alias:
                    self.role_agent_window_open = True
                    self._mutate(
                        stage=f"role-agent quiesce {node.alias}",
                        action=lambda node=node, phase=quiesce_phase: self._role_agent(
                            phase, node
                        ),
                        enter_roll_forward=True,
                    )
                    # Provisioning mutates root-owned host state. A lost remote
                    # response cannot prove that it made no durable progress.
                    self._mutate(
                        stage=f"provision-node {node.alias}",
                        action=lambda node=node: self._fenced_provision(node),
                        enter_roll_forward=True,
                    )
                    self._mutate(
                        stage=f"role-agent resume {node.alias}",
                        action=lambda node=node: self._role_agent(
                            "resume-primary", node
                        ),
                    )
                    self.role_agent_window_open = False
                else:
                    self._run_with_standby_agent_quiesced(
                        node=node,
                        stage="provision-node",
                        action=lambda node=node: self._maintenance(
                            "provision-node", node
                        ),
                    )
            for node in ordered_nodes:
                configure = lambda node=node: self._secret("configure-node", node)
                if node.alias == baseline.standby.alias:
                    self._run_with_standby_agent_quiesced(
                        node=node,
                        stage="configure-node",
                        action=configure,
                    )
                else:
                    self._mutate(
                        stage=f"configure-node {node.alias}",
                        action=configure,
                    )
            for node in ordered_nodes:
                scrub = lambda node=node: self._maintenance("scrub-node", node)
                if node.alias == baseline.standby.alias:
                    self._run_with_standby_agent_quiesced(
                        node=node,
                        stage="scrub-node",
                        action=scrub,
                    )
                else:
                    self._mutate(
                        stage=f"scrub-node {node.alias}",
                        action=scrub,
                    )
            for node in ordered_nodes:
                enable_archive = lambda node=node: self._maintenance(
                    "enable-archive-env", node
                )
                if node.alias == baseline.standby.alias:
                    self._run_with_standby_agent_quiesced(
                        node=node,
                        stage="enable-archive-env",
                        action=enable_archive,
                    )
                else:
                    self._mutate(
                        stage=f"enable-archive-env {node.alias}",
                        action=enable_archive,
                    )
            self._mutate(
                stage=f"basebackup {baseline.primary.alias}",
                action=lambda: self._maintenance("basebackup", baseline.primary),
            )
            self._mutate(
                stage=f"restore-drill {baseline.primary.alias}",
                action=lambda: self._maintenance("restore-drill", baseline.primary),
            )
            for node in ordered_nodes:
                self._mutate(
                    stage=f"bundle finalize {node.alias}",
                    action=lambda node=node: self._release("finalize", node),
                )
            for node in ordered_nodes:
                # Finalization removes the maintenance marker. The sole active
                # role agent now owns timer activation/fencing. Re-running its
                # pinned convergence proof is idempotent and bounded. The
                # following strict verify uses bounded shared-lock arbitration
                # if the first recurring WAL upload starts at the same instant.
                self._mutate(
                    stage=f"role-agent final convergence {node.alias}",
                    action=lambda node=node: self._role_agent(
                        (
                            "resume-standby"
                            if node.alias == baseline.standby.alias
                            else "resume-primary"
                        ),
                        node,
                    ),
                )
            self._mutate(
                stage=f"verify {baseline.primary.alias}",
                action=lambda: self._maintenance("verify", baseline.primary),
            )
        except BaseException as exc:
            if not self.roll_forward:
                self._rollback_owned_bundles(exc)
                raise RuntimeError(
                    f"cluster migration failed before configuration and release bundles "
                    f"were rolled back: {exc}"
                ) from exc
            if self.role_agent_window_open:
                raise self._resume_role_agents_after_failure(
                    baseline, exc
                ) from exc
            raise RuntimeError(
                "cluster migration entered roll-forward state; do not roll back; "
                f"resume with the same transaction ID {self.transaction_id}: {exc}"
            ) from exc
        return MigrationResult(
            transaction_id=self.transaction_id,
            primary_alias=baseline.primary.alias,
            standby_alias=baseline.standby.alias,
            system_identifier=baseline.system_identifier,
            timeline=baseline.timeline,
        )


def migrate_cluster(
    *,
    context: PinnedSshContext,
    env_text: str,
    transaction_id: str,
    runner: Runner,
    dependencies: MigrationDependencies | None = None,
    bootstrap_helper: str = DEFAULT_BOOTSTRAP_HELPER,
) -> MigrationResult:
    """Run or safely resume the reviewed cluster migration transaction."""
    return _MigrationOrchestrator(
        context=context,
        env_text=env_text,
        transaction_id=transaction_id,
        runner=runner,
        dependencies=dependencies or MigrationDependencies(),
        bootstrap_helper=bootstrap_helper,
    ).run()
