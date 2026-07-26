"""Source-bound local inputs for the Patroni rollout controller."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

try:
    from scripts.ha.patroni_compose_db_contract import contract_digest
    from scripts.ha.patroni_rollout_schema import NODE_CONTRACTS
    from scripts.ha.pitr_pinned_ssh import PATRONI_NODES, ssh_subprocess_environment
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from patroni_compose_db_contract import contract_digest  # type: ignore[no-redef]
    from patroni_rollout_schema import NODE_CONTRACTS  # type: ignore[no-redef]
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PATRONI_NODES,
        ssh_subprocess_environment,
    )


REVIEWED_ASSETS = (
    "deploy/ha/mvn-api/docker-compose.patroni.yml",
    "deploy/ha/zakup/docker-compose.patroni.yml",
    "deploy/ha/patroni/archive_wal.py",
    "scripts/ha/patroni_compose_db_contract.py",
    "scripts/ha/check_etcd_quorum.sh",
    "scripts/ha/patroni_rollout_cli.py",
    "scripts/ha/patroni_rollout_journal.py",
    "scripts/ha/patroni_rollout_local.py",
    "scripts/ha/patroni_rollout_model.py",
    "scripts/ha/patroni_rollout_remote.py",
    "scripts/ha/patroni_rollout_remote_contract.py",
    "scripts/ha/patroni_rollout_remote_executor.py",
    "scripts/ha/patroni_rollout_remote_prelude.py",
    "scripts/ha/patroni_rollout_remote_runtime.py",
    "scripts/ha/patroni_rollout_schema.py",
    "scripts/ha/patroni_preflight_incident_recovery.py",
    "scripts/ha/patroni_preflight_recovery_remote.py",
    "scripts/ha/pitr_cluster_topology.py",
    "scripts/ha/pitr_pinned_ssh.py",
    "scripts/ha/patroni_role_agent.py",
    "scripts/ha/patroni_compose_runtime.py",
    "scripts/ha/patroni_role_agent_config.py",
    "scripts/ha/patroni_local_identity.py",
    "deploy/ha/patroni/mvn-patroni-role-agent.service",
    "deploy/ha/security/mvn-api-ssh-host-key.pub",
    "deploy/ha/security/zakup-ssh-host-key.pub",
    "scripts/ha/rollout_patroni_image.py",
    "scripts/ha/recover_patroni_preflight_incident.py",
    "deploy/ha/patroni/incidents/1053e46eb933ebaaffed042ac1b73170.json",
)


def default_runner(
    args: list[str] | tuple[str, ...], stdin: str | None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env=ssh_subprocess_environment(),
        timeout=900,
    )


def _prove_reviewed_checkout(repo_root: Path, deploy_sha: str) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    if head.returncode != 0 or head.stdout.strip() != deploy_sha:
        raise RuntimeError("checked-out controller HEAD does not equal the tested deploy SHA")
    for relative in REVIEWED_ASSETS:
        committed = subprocess.run(
            ["git", "show", f"{deploy_sha}:{relative}"],
            cwd=repo_root,
            capture_output=True,
            check=False,
            timeout=10,
        )
        local = repo_root / relative
        if committed.returncode != 0 or not local.is_file() or local.read_bytes() != committed.stdout:
            raise RuntimeError(f"reviewed rollout asset differs from tested SHA: {relative}")


def local_contract_digests(deploy_sha: str) -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[2]
    _prove_reviewed_checkout(repo_root, deploy_sha)
    digests: dict[str, str] = {}
    for node in PATRONI_NODES:
        node_contract = NODE_CONTRACTS[node.alias]
        project_name = str(node_contract["compose_project"])
        project_dir = str(node_contract["project_dir"])
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--project-name",
                project_name,
                "--project-directory",
                project_dir,
                "-f",
                str(node.compose_source),
                "config",
                "--no-env-resolution",
                "--no-interpolate",
                "--format",
                "json",
            ],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"could not render tracked Compose contract for {node.alias}: "
                f"{(result.stderr or result.stdout).strip()}"
            )
        try:
            config = json.loads(result.stdout)
        except ValueError as exc:
            raise RuntimeError(f"tracked Compose output is invalid for {node.alias}") from exc
        if not isinstance(config, dict):
            raise RuntimeError(f"tracked Compose output is not an object for {node.alias}")
        digests[node.alias] = contract_digest(config)
    return digests
