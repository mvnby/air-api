"""Command-line adapter for the Patroni rollout orchestrator."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

try:
    from scripts.ha.patroni_rollout_schema import RolloutInputs
    from scripts.ha.pitr_pinned_ssh import (
        PATRONI_NODES,
        create_context,
        validate_effective_config,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from patroni_rollout_schema import RolloutInputs  # type: ignore[no-redef]
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PATRONI_NODES,
        create_context,
        validate_effective_config,
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deploy-sha", required=True)
    parser.add_argument("--publish-run-id", required=True)
    parser.add_argument("--publish-run-attempt", required=True, type=int)
    parser.add_argument("--transaction-id", required=True)
    parser.add_argument("--maintenance-transaction-id", required=True)
    parser.add_argument("--current-image", required=True)
    parser.add_argument("--target-image", required=True)
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument("--apply", required=True, choices=("true", "false"))
    parser.add_argument("--resume", required=True, choices=("true", "false"))
    return parser.parse_args()


def main(rollout: Callable[..., object]) -> int:
    args = _arguments()
    inputs = RolloutInputs.validated(
        deploy_sha=args.deploy_sha,
        publish_run_id=args.publish_run_id,
        publish_run_attempt=args.publish_run_attempt,
        transaction_id=args.transaction_id,
        maintenance_transaction_id=args.maintenance_transaction_id,
        current_image=args.current_image,
        target_image=args.target_image,
        apply=args.apply == "true",
        resume=args.resume == "true",
    )
    with tempfile.TemporaryDirectory(prefix="mvn-patroni-ssh-") as raw_directory:
        directory = Path(raw_directory)
        directory.chmod(0o700)
        context = create_context(directory, args.identity_file)
        for node in PATRONI_NODES:
            validate_effective_config(node, context)
        result = rollout(
            context=context,
            inputs=inputs,
            ghcr_username=os.environ.get("GHCR_USERNAME", ""),
            ghcr_token=os.environ.get("GHCR_TOKEN", ""),
        )
    print(json.dumps(result.__dict__, sort_keys=True, separators=(",", ":")))
    return 0
