"""CLI orchestration for the production Patroni checker."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

try:
    from scripts.ha import check_patroni_production as checks
    from scripts.ha.patroni_notification_snapshot import (
        build_notification_snapshot,
        failure_snapshot,
        write_snapshot,
    )
except ModuleNotFoundError:
    import check_patroni_production as checks  # type: ignore[no-redef]
    from patroni_notification_snapshot import (  # type: ignore[no-redef]
        build_notification_snapshot,
        failure_snapshot,
        write_snapshot,
    )


def perform_checks_with_topology(
    config: checks.CheckerConfig, runner: checks.SshRunner
) -> tuple[checks.Report, checks.NodeConfig, checks.NodeConfig]:
    report = checks.Report()
    payloads = checks.probe_nodes(config, runner)
    primary, standby = checks.select_primary(config.nodes, payloads)
    report.pass_check(
        f"exactly one Patroni primary: {primary.label} ({primary.patroni_name})"
    )

    checks._check_cluster_views(config, runner, primary, standby, report)
    checks._check_postgres(config, runner, primary, standby, report)
    checks._check_runtime(config, runner, primary, standby, report)

    etcd = runner.run(config.api, config.etcd_check_command, check=False)
    if etcd.returncode == 0 and "etcd_quorum_status=passed members=3" in etcd.stdout:
        report.pass_check("etcd quorum has three healthy members")
    else:
        detail = (etcd.stderr or etcd.stdout or "check failed").strip().replace("\n", " ")
        report.fail(f"etcd quorum check failed: {detail}")
    return report, primary, standby


def perform_checks(
    config: checks.CheckerConfig, runner: checks.SshRunner
) -> checks.Report:
    report, _, _ = perform_checks_with_topology(config, runner)
    return report


def _print_report(report: checks.Report) -> None:
    for message in report.ok:
        print(f"[patroni-production][ok] {message}")
    for message in report.failures:
        print(f"[patroni-production][fail] {message}")
    status = "failed" if report.failures else "passed"
    print(
        f"[patroni-production][summary] status={status} "
        f"ok={len(report.ok)} failures={len(report.failures)}"
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=checks.__doc__)
    parser.add_argument(
        "--resolve-primary",
        action="store_true",
        help="Print only api or reserve after validating the two Patroni roles.",
    )
    parser.add_argument(
        "--snapshot-output",
        type=Path,
        help="Write a secret-free JSON observation for owner-facing HA notifications.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        config = checks.load_config()
        runner = checks.SshRunner(config.ssh_options)
        if args.resolve_primary:
            primary, _ = checks.select_primary(
                config.nodes, checks.probe_nodes(config, runner)
            )
            print(primary.label)
            return 0
        report, primary, standby = perform_checks_with_topology(config, runner)
        write_snapshot(
            args.snapshot_output,
            build_notification_snapshot(
                config,
                runner,
                report,
                primary,
                standby,
                cluster_loader=checks._json_remote,
                ready_loader=checks._ready_response,
            ),
        )
    except (RuntimeError, ValueError) as exc:
        write_snapshot(args.snapshot_output, failure_snapshot(exc))
        if args.resolve_primary:
            print(f"could not resolve Patroni primary: {exc}", file=sys.stderr)
        else:
            print(f"[patroni-production][fail] {exc}")
            print("[patroni-production][summary] status=failed ok=0 failures=1")
        return 2

    _print_report(report)
    return 1 if report.failures else 0
