#!/usr/bin/env python3
"""Roll out the exact reviewed PITR host-asset release to both Patroni nodes."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

try:
    from scripts.ha.pitr_host_asset_rollout import (
        rollout_host_assets,
        validate_transaction_id,
    )
    from scripts.ha.pitr_pinned_ssh import (
        PATRONI_NODES,
        create_context,
        ssh_subprocess_environment,
        validate_effective_config,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_host_asset_rollout import (  # type: ignore[no-redef]
        rollout_host_assets,
        validate_transaction_id,
    )
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PATRONI_NODES,
        create_context,
        ssh_subprocess_environment,
        validate_effective_config,
    )


def log(stage: str, message: str) -> None:
    print(f"[pitr-host-assets][{stage}] {message}")


def _run_subprocess(
    args: Sequence[str],
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env=ssh_subprocess_environment(),
    )


def _validate_owner_only_regular_file(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} not found: {path}") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise RuntimeError(
            f"{label} must be an owner-only regular non-symlink file"
        )


def validate_identity_file(raw_path: str) -> Path:
    if not raw_path.strip():
        raise RuntimeError("--identity-file is required")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise RuntimeError("SSH identity file must use an absolute path")
    _validate_owner_only_regular_file(path, label="SSH identity file")
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--identity-file",
        required=True,
        help="Owner-only SSH key used with repository-pinned host identities.",
    )
    parser.add_argument(
        "--transaction-id",
        required=True,
        help=(
            "Stable 32-character lowercase hexadecimal rollout ID. Reuse the "
            "same ID after any ambiguous failure."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        transaction_id = validate_transaction_id(args.transaction_id)
        identity_file = validate_identity_file(args.identity_file)
        with tempfile.TemporaryDirectory(
            prefix="mvn-pitr-host-assets-"
        ) as temporary:
            directory = Path(temporary)
            directory.chmod(0o700)
            context = create_context(directory, identity_file)
            for node in PATRONI_NODES:
                validate_effective_config(node, context)

            result = rollout_host_assets(
                context=context,
                transaction_id=transaction_id,
                runner=_run_subprocess,
            )

        releases = ",".join(
            f"{alias}:{digest}" for alias, digest in result.release_digests
        )
        log(
            "ok",
            "rollout passed "
            f"transaction={result.transaction_id} "
            f"primary={result.primary_alias} "
            f"standby={result.standby_alias} "
            f"timeline={result.timeline} "
            f"profile={result.compose_profile} "
            f"releases={releases}",
        )
        return 0
    except RuntimeError as exc:
        log("fail", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
