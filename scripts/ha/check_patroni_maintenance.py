#!/usr/bin/env python3
"""Report a valid official Patroni maintenance window through both SSH nodes."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

try:
    from scripts.ha.check_patroni_production import SshRunner, load_config
    from scripts.ha.patroni_maintenance_window import (
        DEFAULT_MAX_AGE_SECONDS,
        REMOTE_PROBE,
        detect_window,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from check_patroni_production import SshRunner, load_config  # type: ignore[no-redef]
    from patroni_maintenance_window import (  # type: ignore[no-redef]
        DEFAULT_MAX_AGE_SECONDS,
        REMOTE_PROBE,
        detect_window,
    )


def _max_age_seconds() -> int:
    raw = os.getenv(
        "PATRONI_MAINTENANCE_MAX_AGE_SECONDS", str(DEFAULT_MAX_AGE_SECONDS)
    ).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            "PATRONI_MAINTENANCE_MAX_AGE_SECONDS must be an integer"
        ) from exc
    if value < 60:
        raise ValueError(
            "PATRONI_MAINTENANCE_MAX_AGE_SECONDS must be at least 60"
        )
    return value


def _write_github_output(path: str, *, active: bool, transaction_id: str) -> None:
    if not path:
        return
    output = Path(path)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(f"active={'true' if active else 'false'}\n")
        handle.write(f"transaction_id={transaction_id}\n")


def run(*, github_output: str = "") -> int:
    config = load_config()
    ssh = SshRunner(config.ssh_options)
    node_by_label = {node.label: node for node in config.nodes}

    def remote(target: str, source: str):
        if source != REMOTE_PROBE:
            raise RuntimeError("unreviewed maintenance probe source")
        return ssh.run(
            node_by_label[target],
            "exec /usr/bin/python3 -I -",
            stdin=source,
            check=False,
        )

    window = detect_window(
        tuple((node.label, node.label) for node in config.nodes),
        runner=remote,
        max_age_seconds=_max_age_seconds(),
    )
    _write_github_output(
        github_output,
        active=window.active,
        transaction_id=window.transaction_id,
    )
    if window.active:
        print(
            "[patroni-maintenance][status] active=true "
            f"transaction={window.transaction_id} age_seconds={window.age_seconds} "
            "nodes=2 pitr_timers=fenced"
        )
    else:
        print("[patroni-maintenance][status] active=false nodes=2")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--github-output",
        default="",
        help="Append active and transaction_id outputs to this GitHub output file",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(github_output=args.github_output)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[patroni-maintenance][error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
