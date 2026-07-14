#!/usr/bin/env python3
"""Fail-closed standby-first rollout of one exact Patroni image digest."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

try:
    from scripts.ha.patroni_rollout_journal import (
        completed_flags,
        has_ambiguous_switchover_boundary,
        record_flags,
    )
    from scripts.ha.patroni_rollout_remote import (
        helper_source_sha256,
        read_status,
        run_remote_action,
    )
    from scripts.ha.patroni_rollout_local import default_runner, local_contract_digests
    from scripts.ha.patroni_rollout_schema import RolloutInputs, SHA256_RE
    from scripts.ha.pitr_cluster_topology import ClusterTopology, discover_cluster_topology
    from scripts.ha.pitr_pinned_ssh import (
        PATRONI_NODES,
        PatroniNode,
        PinnedSshContext,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from patroni_rollout_journal import (  # type: ignore[no-redef]
        completed_flags,
        has_ambiguous_switchover_boundary,
        record_flags,
    )
    from patroni_rollout_remote import (  # type: ignore[no-redef]
        helper_source_sha256,
        read_status,
        run_remote_action,
    )
    from patroni_rollout_local import (  # type: ignore[no-redef]
        default_runner,
        local_contract_digests,
    )
    from patroni_rollout_schema import (  # type: ignore[no-redef]
        RolloutInputs,
        SHA256_RE,
    )
    from pitr_cluster_topology import (  # type: ignore[no-redef]
        ClusterTopology,
        discover_cluster_topology,
    )
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PATRONI_NODES,
        PatroniNode,
        PinnedSshContext,
    )


Runner = Callable[[Sequence[str], str | None], object]
Discoverer = Callable[..., ClusterTopology]
RemoteAction = Callable[..., str]
StatusReader = Callable[..., dict[str, object]]
Sleeper = Callable[[float], None]
NODE_ALIASES = tuple(node.alias for node in PATRONI_NODES)


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


class _SafeAbort(RuntimeError):
    """Raised after the old generation is fully proved and unfenced."""


class _Orchestrator:
    def __init__(
        self,
        *,
        context: PinnedSshContext,
        inputs: RolloutInputs,
        contract_digests: Mapping[str, str],
        ghcr_username: str,
        ghcr_token: str,
        runner: Runner,
        dependencies: RolloutDependencies,
        helper_digest: str,
    ) -> None:
        if set(contract_digests) != {node.alias for node in PATRONI_NODES}:
            raise RuntimeError("both reviewed Compose contract digests are required")
        if any(not SHA256_RE.fullmatch(value) for value in contract_digests.values()):
            raise RuntimeError("Compose contract digests must be lowercase SHA-256")
        if not ghcr_username or not ghcr_token or "\0" in ghcr_token:
            raise RuntimeError("GHCR read credentials are required")
        self.context = context
        self.inputs = inputs
        self.contracts = dict(contract_digests)
        self.ghcr_username = ghcr_username
        self.ghcr_token = ghcr_token
        self.runner = runner
        self.dependencies = dependencies
        self.helper_digest = helper_digest
        self.nodes = {node.alias: node for node in PATRONI_NODES}
        self.original: ClusterTopology | None = None
        self.roll_forward = False
        self.db_mutation_attempted = False

    def _discover(self) -> ClusterTopology:
        return self.dependencies.discover(context=self.context, runner=self.runner)

    def _remote(
        self, action: str, node: PatroniNode, *, extra: Mapping[str, str] | None = None
    ) -> str:
        return self.dependencies.remote(
            action=action,
            node=node,
            context=self.context,
            inputs=self.inputs,
            compose_contract_sha256=self.contracts[node.alias],
            helper_sha256=self.helper_digest,
            extra=extra,
            runner=self.runner,
        )

    def _status(self, node: PatroniNode) -> dict[str, object]:
        return self.dependencies.status(
            node=node,
            context=self.context,
            inputs=self.inputs,
            compose_contract_sha256=self.contracts[node.alias],
            helper_sha256=self.helper_digest,
            runner=self.runner,
        )

    def _record(self, name: str) -> None:
        for node in PATRONI_NODES:
            self._remote("record", node, extra={"record": name})

    def _statuses(self) -> dict[str, dict[str, object]]:
        return {node.alias: self._status(node) for node in PATRONI_NODES}

    def _ensure_record(
        self, statuses: dict[str, dict[str, object]], name: str
    ) -> dict[str, dict[str, object]]:
        if not all(record_flags(statuses, NODE_ALIASES, name)):
            self._record(name)
            return self._statuses()
        return statuses

    def _has_record(self, statuses: Mapping[str, Mapping[str, object]], name: str) -> bool:
        return all(record_flags(statuses, NODE_ALIASES, name))

    def _complete_interrupted_records(
        self, statuses: dict[str, dict[str, object]]
    ) -> dict[str, dict[str, object]]:
        for node in PATRONI_NODES:
            operation = statuses[node.alias].get("operation")
            if isinstance(operation, str) and operation.startswith("record:"):
                name = operation.removeprefix("record:")
                self._remote("record", node, extra={"record": name})
        return self._statuses()

    def _resume_terminal_operations(
        self, statuses: dict[str, dict[str, object]]
    ) -> dict[str, dict[str, object]]:
        operations = {node.alias: statuses[node.alias].get("operation") for node in PATRONI_NODES}
        revert_in_progress = "revert-archive-command" in operations.values()
        revert_completed = any(
            completed_flags(statuses, NODE_ALIASES, "revert-archive-command")
        )
        if revert_in_progress or revert_completed:
            conflicting = {
                node: operation
                for node, operation in operations.items()
                if operation not in {"idle", "revert-archive-command"}
            }
            if conflicting:
                raise RuntimeError(
                    "DCS compensation journal conflicts with another interrupted operation"
                )
            for node in PATRONI_NODES:
                if operations[node.alias] == "revert-archive-command":
                    self._remote("revert-archive-command", node)
            reconciled = self._statuses()
            if not any(
                completed_flags(reconciled, NODE_ALIASES, "revert-archive-command")
            ):
                raise RuntimeError("DCS compensation did not reach a completed journal state")
            return self._ensure_record(reconciled, "archive-command-reverted")
        abort_completed = any(
            "abort" in statuses[node.alias].get("completed", [])
            for node in PATRONI_NODES
        )
        if "abort" in operations.values() or abort_completed:
            assert self.original is not None
            for node in (self.original.standby, self.original.primary):
                self._remote("abort", node)
            raise RuntimeError("aborted Patroni rollout transaction was reconciled")
        rollback_completed = any(
            "rollback-node" in statuses[node.alias].get("completed", [])
            for node in PATRONI_NODES
        )
        if "rollback-node" in operations.values() or rollback_completed:
            assert self.original is not None
            self._remote(
                "rollback-node",
                self.original.standby,
                extra={
                    "expected_primary": self.original.primary.alias,
                    "expected_role": "standby",
                    "update_phase": "rollback",
                },
            )
            for node in (self.original.standby, self.original.primary):
                self._remote("abort", node)
            raise RuntimeError("interrupted pre-switchover rollback was reconciled")
        if "update-node" in operations.values():
            assert self.original is not None
            if self._has_record(statuses, "switched-over"):
                self._remote(
                    "update-node",
                    self.original.primary,
                    extra={
                        "expected_primary": self.original.standby.alias,
                        "expected_role": "standby",
                        "update_phase": "former-primary",
                    },
                )
                return self._statuses()
            self._remote(
                "rollback-node",
                self.original.standby,
                extra={
                    "expected_primary": self.original.primary.alias,
                    "expected_role": "standby",
                    "update_phase": "rollback",
                },
            )
            for node in (self.original.standby, self.original.primary):
                self._remote("abort", node)
            raise RuntimeError("interrupted pre-switchover update was rolled back")
        return statuses

    def _wait_topology(
        self,
        *,
        primary_alias: str,
        system_identifier: str,
        timeline: int,
        attempts: int = 30,
    ) -> ClusterTopology:
        last_error: BaseException | None = None
        for attempt in range(attempts):
            try:
                topology = self._discover()
                if (
                    topology.primary.alias == primary_alias
                    and topology.system_identifier == system_identifier
                    and topology.timeline == timeline
                ):
                    return topology
                last_error = RuntimeError(
                    "topology does not match the exact expected primary/lineage"
                )
            except BaseException as exc:
                last_error = exc
            if attempt + 1 < attempts:
                self.dependencies.sleep(2)
        raise RuntimeError(f"timed out proving Patroni topology: {last_error}")

    def _prepare(
        self, initial: ClusterTopology | None
    ) -> dict[str, dict[str, object]]:
        prior = {node.alias: self._status(node) for node in PATRONI_NODES}
        existing = [
            status for status in prior.values() if status.get("status") != "missing"
        ]
        if self.inputs.resume:
            if not existing:
                raise RuntimeError("resume=true requires an existing journal on at least one node")
            reference = existing[0]
            baseline_primary = reference.get("baseline_primary")
            baseline_system = reference.get("baseline_system_identifier")
            baseline_timeline = reference.get("baseline_timeline")
            if (
                baseline_primary not in self.nodes
                or not isinstance(baseline_system, str)
                or not re.fullmatch(r"[0-9]{10,24}", baseline_system)
                or type(baseline_timeline) is not int
                or baseline_timeline <= 0
            ):
                raise RuntimeError("existing rollout baseline is invalid")
            initial = ClusterTopology(
                primary=self.nodes[baseline_primary],
                standby=self.nodes[
                    "zakup" if baseline_primary == "mvn-api" else "mvn-api"
                ],
                system_identifier=baseline_system,
                timeline=baseline_timeline,
            )
        elif existing:
            raise RuntimeError("existing transaction journals require resume=true")
        elif initial is None:
            raise RuntimeError("new rollout requires a proved initial topology")
        assert initial is not None
        extra = {
            "baseline_primary": initial.primary.alias,
            "baseline_system_identifier": initial.system_identifier,
            "baseline_timeline": str(initial.timeline),
        }
        prepared: list[PatroniNode] = []
        try:
            for node in PATRONI_NODES:
                completed = prior[node.alias].get("completed", [])
                if isinstance(completed, list) and "finalize" in completed:
                    continue
                self._remote("prepare", node, extra=extra)
                prepared.append(node)
        except BaseException as exc:
            if self.inputs.resume:
                raise RuntimeError(
                    f"could not resume both rollout journals: {exc}; "
                    "existing transaction remains fenced"
                ) from exc
            cleanup_errors = []
            for node in reversed(prepared):
                try:
                    self._remote("abort", node)
                except BaseException as cleanup_error:
                    cleanup_errors.append(f"{node.alias}: {cleanup_error}")
            detail = "; ".join(cleanup_errors) or "prepared nodes were unfenced"
            raise RuntimeError(f"could not prepare both rollout journals: {exc}; {detail}") from exc
        statuses = {node.alias: self._status(node) for node in PATRONI_NODES}
        baselines = {
            (
                status.get("baseline_primary"),
                status.get("baseline_system_identifier"),
                status.get("baseline_timeline"),
            )
            for status in statuses.values()
        }
        if len(baselines) != 1:
            raise RuntimeError("per-host rollout journals disagree on baseline lineage")
        primary, system_identifier, timeline = next(iter(baselines))
        if (
            primary not in self.nodes
            or not isinstance(system_identifier, str)
            or not re.fullmatch(r"[0-9]{10,24}", system_identifier)
            or type(timeline) is not int
            or timeline <= 0
        ):
            raise RuntimeError("rollout journal baseline lineage is invalid")
        standby = self.nodes["zakup" if primary == "mvn-api" else "mvn-api"]
        self.original = ClusterTopology(
            primary=self.nodes[primary],
            standby=standby,
            system_identifier=system_identifier,
            timeline=timeline,
        )
        return statuses

    def _resume_finalization(
        self, statuses: dict[str, dict[str, object]]
    ) -> RolloutResult | None:
        assert self.original is not None
        finalized = [
            "finalize" in statuses[node.alias].get("completed", [])
            for node in PATRONI_NODES
        ]
        if not any(finalized):
            return None
        if not self.inputs.resume:
            raise RuntimeError("partial finalization requires resume=true")
        if not self._has_record(statuses, "final-proved"):
            raise RuntimeError("finalized rollout journals lack the shared final proof")
        original = self.original
        final = self._wait_topology(
            primary_alias=original.standby.alias,
            system_identifier=original.system_identifier,
            timeline=original.timeline + 1,
        )
        for node in (original.primary, original.standby):
            self._remote("finalize", node)
        return RolloutResult(
            transaction_id=self.inputs.transaction_id,
            original_primary=original.primary.alias,
            final_primary=final.primary.alias,
            target_image=self.inputs.target_image,
            system_identifier=final.system_identifier,
            timeline=final.timeline,
        )

    def _rollback_before_switchover(self, original_error: BaseException) -> None:
        assert self.original is not None
        try:
            if self.db_mutation_attempted:
                self._remote(
                    "rollback-node",
                    self.original.standby,
                    extra={
                        "expected_primary": self.original.primary.alias,
                        "expected_role": "standby",
                        "update_phase": "rollback",
                    },
                )
                self._wait_topology(
                    primary_alias=self.original.primary.alias,
                    system_identifier=self.original.system_identifier,
                    timeline=self.original.timeline,
                    attempts=10,
                )
            for node in (self.original.standby, self.original.primary):
                self._remote("abort", node)
        except BaseException as rollback_error:
            raise RuntimeError(
                f"rollout failed before switchover: {original_error}; safe rollback "
                f"could not be proved and cutover markers remain: {rollback_error}"
            ) from original_error
        raise RuntimeError(
            f"rollout failed before switchover and the old image/DCS generation was restored: {original_error}"
        ) from original_error

    def run(self) -> RolloutResult:
        initial = None if self.inputs.resume else self._discover()
        statuses = self._prepare(initial)
        assert self.original is not None
        original = self.original
        baseline_record = "baseline-primary-" + original.primary.alias
        statuses = self._complete_interrupted_records(statuses)
        finalized = self._resume_finalization(statuses)
        if finalized is not None:
            return finalized
        statuses = self._resume_terminal_operations(statuses)
        if self.inputs.resume and has_ambiguous_switchover_boundary(
            statuses, NODE_ALIASES
        ):
            self.roll_forward = True
        try:
            statuses = self._ensure_record(statuses, baseline_record)
            for node in PATRONI_NODES:
                self._remote("preflight", node)
                self._remote(
                    "stage",
                    node,
                    extra={
                        "ghcr_token": self.ghcr_token,
                        "ghcr_username": self.ghcr_username,
                    },
                )
            statuses = self._statuses()
            current = self._discover()
            if current.system_identifier != original.system_identifier:
                raise RuntimeError("PostgreSQL system identifier drifted")
            switched_record = self._has_record(statuses, "switched-over")
            live_pre_boundary = (
                current.primary.alias == original.primary.alias
                and current.standby.alias == original.standby.alias
                and current.timeline == original.timeline
            )
            live_post_boundary = (
                current.primary.alias == original.standby.alias
                and current.standby.alias == original.primary.alias
                and current.timeline == original.timeline + 1
            )
            if not live_pre_boundary and not live_post_boundary:
                raise RuntimeError("live topology is outside both reviewed rollout generations")
            if switched_record and not live_post_boundary:
                raise RuntimeError("journal says switched-over but live topology disagrees")
            switched = switched_record or live_post_boundary
            if switched:
                if not switched_record:
                    try:
                        self._remote("attest-target-runtime", current.primary)
                    except BaseException as target_error:
                        try:
                            for node in PATRONI_NODES:
                                self._remote("attest-current-runtime", node)
                            self._remote("check-legacy-dcs", current.primary)
                            for node in PATRONI_NODES:
                                self._remote("abort", node)
                        except BaseException as mixed_error:
                            raise RuntimeError(
                                "unrecorded external failover left an unproved image generation; "
                                f"transaction remains fenced: {target_error}; {mixed_error}"
                            ) from target_error
                        raise _SafeAbort(
                            "external failover occurred before image rollout; old images/DCS were "
                            "proved and rollout markers removed; start a new transaction"
                        )
                self.roll_forward = True
                current = self._wait_topology(
                    primary_alias=original.standby.alias,
                    system_identifier=original.system_identifier,
                    timeline=original.timeline + 1,
                )
                if not switched_record:
                    statuses = self._ensure_record(statuses, "switched-over")
            else:
                current = self._wait_topology(
                    primary_alias=original.primary.alias,
                    system_identifier=original.system_identifier,
                    timeline=original.timeline,
                )
                self._remote("check-legacy-dcs", current.primary)
                if not self._has_record(statuses, "standby-updated"):
                    self.db_mutation_attempted = True
                    self._remote(
                        "update-node",
                        original.standby,
                        extra={
                            "expected_primary": original.primary.alias,
                            "expected_role": "standby",
                            "update_phase": "standby",
                        },
                    )
                self._wait_topology(
                    primary_alias=original.primary.alias,
                    system_identifier=original.system_identifier,
                    timeline=original.timeline,
                )
                statuses = self._ensure_record(self._statuses(), "standby-updated")
                self._remote("attest-target-runtime", original.standby)
                # A lost response can hide a committed switchover. From this
                # point onward rollback is forbidden; discovery decides resume.
                self.roll_forward = True
                try:
                    self._remote(
                        "switchover",
                        original.primary,
                        extra={
                            "candidate": original.standby.alias,
                            "expected_primary": original.primary.alias,
                        },
                    )
                except BaseException:
                    current = self._wait_topology(
                        primary_alias=original.standby.alias,
                        system_identifier=original.system_identifier,
                        timeline=original.timeline + 1,
                    )
                else:
                    current = self._wait_topology(
                        primary_alias=original.standby.alias,
                        system_identifier=original.system_identifier,
                        timeline=original.timeline + 1,
                    )
                statuses = self._ensure_record(self._statuses(), "switched-over")

            if not self._has_record(statuses, "former-primary-updated"):
                self._remote(
                    "update-node",
                    original.primary,
                    extra={
                        "expected_primary": original.standby.alias,
                        "expected_role": "standby",
                        "update_phase": "former-primary",
                    },
                )
            current = self._wait_topology(
                primary_alias=original.standby.alias,
                system_identifier=original.system_identifier,
                timeline=original.timeline + 1,
            )
            statuses = self._ensure_record(self._statuses(), "former-primary-updated")
            for node in PATRONI_NODES:
                self._remote("attest-target-runtime", node)
                self._remote(
                    "attest-runtime-ownership",
                    node,
                    extra={
                        "expected_role": "primary"
                        if node.alias == original.standby.alias
                        else "standby"
                    },
                )
            command_was_reverted = any(
                record_flags(statuses, NODE_ALIASES, "archive-command-reverted")
            )
            if command_was_reverted or not self._has_record(
                statuses, "archive-command-applied"
            ):
                self._remote("prove-etcd", current.primary)
                self._remote("apply-archive-command", current.primary)
            self._remote("check-target-dcs", current.primary)
            statuses = self._ensure_record(self._statuses(), "archive-command-applied")
            for node in PATRONI_NODES:
                self._remote("attest-archive-runtime", node)
            if not self._has_record(statuses, "archive-proved"):
                try:
                    self._remote("prove-archive", current.primary)
                except BaseException as proof_error:
                    try:
                        self._remote("revert-archive-command", current.primary)
                        statuses = self._ensure_record(
                            self._statuses(), "archive-command-reverted"
                        )
                    except BaseException as compensation_error:
                        raise RuntimeError(
                            "archive helper proof failed and compensating legacy DCS "
                            f"reversion could not be proved: {proof_error}; {compensation_error}"
                        ) from proof_error
                    raise RuntimeError(
                        "archive helper proof failed; exact legacy archive_command was "
                        f"restored and the transaction remains fenced: {proof_error}"
                    ) from proof_error
                statuses = self._ensure_record(self._statuses(), "archive-proved")
            final = self._wait_topology(
                primary_alias=original.standby.alias,
                system_identifier=original.system_identifier,
                timeline=original.timeline + 1,
            )
            self._remote("check-target-dcs", final.primary)
            for node in PATRONI_NODES:
                self._remote("attest-target-runtime", node)
                self._remote("attest-archive-runtime", node)
                self._remote(
                    "attest-runtime-ownership",
                    node,
                    extra={
                        "expected_role": "primary"
                        if node.alias == original.standby.alias
                        else "standby"
                    },
                )
            self._remote("prove-etcd", final.primary)
            statuses = self._ensure_record(self._statuses(), "final-proved")
            for node in (original.primary, original.standby):
                if "finalize" not in statuses[node.alias].get("completed", []):
                    self._remote("finalize", node)
            return RolloutResult(
                transaction_id=self.inputs.transaction_id,
                original_primary=original.primary.alias,
                final_primary=final.primary.alias,
                target_image=self.inputs.target_image,
                system_identifier=final.system_identifier,
                timeline=final.timeline,
            )
        except _SafeAbort:
            raise
        except BaseException as exc:
            if not self.roll_forward:
                self._rollback_before_switchover(exc)
            raise RuntimeError(
                "Patroni rollout is in roll-forward state; do not roll back images. "
                f"Resume transaction {self.inputs.transaction_id}: {exc}"
            ) from exc


def rollout_patroni_image(
    *,
    context: PinnedSshContext,
    inputs: RolloutInputs,
    ghcr_username: str,
    ghcr_token: str,
    runner: Runner = default_runner,
    dependencies: RolloutDependencies | None = None,
    helper_digest: str | None = None,
) -> RolloutResult:
    return _Orchestrator(
        context=context,
        inputs=inputs,
        contract_digests=local_contract_digests(inputs.deploy_sha),
        ghcr_username=ghcr_username,
        ghcr_token=ghcr_token,
        runner=runner,
        dependencies=dependencies or RolloutDependencies(),
        helper_digest=helper_digest or helper_source_sha256(),
    ).run()


def main() -> int:
    try:
        from scripts.ha.patroni_rollout_cli import main as cli_main
    except ModuleNotFoundError:
        from patroni_rollout_cli import main as cli_main  # type: ignore[no-redef]
    return cli_main(rollout_patroni_image)


if __name__ == "__main__":
    raise SystemExit(main())
