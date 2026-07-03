#!/usr/bin/env python3
"""Summarize MVN API HA status for operators.

The report combines three proof surfaces without printing secret values:

- recent GitHub Actions deploy/monitor results;
- GitHub-side external strict-mode prerequisites;
- the live direct-origin active/passive invariant.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_ha_external_prerequisites import (  # noqa: E402
    check_metadata,
    load_metadata,
)


DEFAULT_REPO = "mvnby/air-api"
DEFAULT_BRANCH = "main"
DEFAULT_PRIMARY_ORIGIN = "185.250.45.54"
DEFAULT_STANDBY_ORIGIN = "193.47.42.213"

Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ExpectedWorkflow:
    name: str
    max_age_hours: float | None = None


@dataclass(frozen=True)
class WorkflowRun:
    workflow_name: str
    display_title: str
    status: str
    conclusion: str
    created_at: datetime | None
    url: str


@dataclass(frozen=True)
class ReportResult:
    ok: list[str]
    warnings: list[str]
    blockers: list[str]
    failures: list[str]

    @property
    def status(self) -> str:
        if self.failures:
            return "failed"
        if self.blockers or self.warnings:
            return "attention"
        return "passed"


EXPECTED_WORKFLOWS = (
    ExpectedWorkflow("Deploy to Production 🚀"),
    ExpectedWorkflow("CI (Test & Lint)"),
    ExpectedWorkflow("API HA Status Report", max_age_hours=3),
    ExpectedWorkflow("API HA Invariant Check", max_age_hours=8),
    ExpectedWorkflow("API HA Readiness Audit", max_age_hours=8),
    ExpectedWorkflow("API VPS Health Check", max_age_hours=8),
    ExpectedWorkflow("Media CDN Check", max_age_hours=8),
    ExpectedWorkflow("PostgreSQL Replication Check", max_age_hours=8),
    ExpectedWorkflow("Cloudflare LB Config Check", max_age_hours=8),
    ExpectedWorkflow("PostgreSQL PITR Check", max_age_hours=8),
    ExpectedWorkflow("API Restore Drill", max_age_hours=36),
    ExpectedWorkflow("PostgreSQL PITR Restore Drill", max_age_hours=36),
)


def log(stage: str, message: str) -> None:
    print(f"[ha-status][{stage}] {message}")


def parse_github_time(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_workflow_run(raw: object) -> WorkflowRun | None:
    if not isinstance(raw, dict):
        return None
    workflow_name = str(raw.get("workflowName") or "").strip()
    if not workflow_name:
        return None
    return WorkflowRun(
        workflow_name=workflow_name,
        display_title=str(raw.get("displayTitle") or "").strip(),
        status=str(raw.get("status") or "").strip(),
        conclusion=str(raw.get("conclusion") or "").strip(),
        created_at=parse_github_time(raw.get("createdAt")),
        url=str(raw.get("url") or "").strip(),
    )


def _run_subprocess(args: Sequence[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def run_checked(args: Sequence[str], *, runner: Runner | None = None) -> str:
    actual_runner = runner or _run_subprocess
    result = actual_runner(args, None)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(output or f"command failed: {' '.join(args)}")
    return result.stdout.strip()


def load_workflow_runs(
    *,
    repo: str,
    branch: str,
    limit: int,
    runner: Runner | None = None,
) -> list[WorkflowRun]:
    output = run_checked(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--branch",
            branch,
            "--limit",
            str(limit),
            "--json",
            "workflowName,displayTitle,status,conclusion,createdAt,url",
        ],
        runner=runner,
    )
    try:
        raw_runs = json.loads(output or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"could not parse gh run list JSON: {output!r}") from exc
    if not isinstance(raw_runs, list):
        raise RuntimeError("unexpected gh run list JSON response")
    return [run for item in raw_runs if (run := parse_workflow_run(item)) is not None]


def latest_runs_by_workflow(runs: Sequence[WorkflowRun]) -> dict[str, WorkflowRun]:
    latest: dict[str, WorkflowRun] = {}
    for run in runs:
        current = latest.get(run.workflow_name)
        if current is None:
            latest[run.workflow_name] = run
            continue
        if current.status != "completed" and run.status == "completed":
            latest[run.workflow_name] = run
    return latest


def age_hours(run: WorkflowRun, *, now: datetime) -> float | None:
    if run.created_at is None:
        return None
    created_at = run.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - created_at).total_seconds() / 3600)


def evaluate_workflows(
    latest: dict[str, WorkflowRun],
    *,
    expected: Sequence[ExpectedWorkflow] = EXPECTED_WORKFLOWS,
    now: datetime | None = None,
) -> ReportResult:
    now = now or datetime.now(timezone.utc)
    ok: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []

    for workflow in expected:
        run = latest.get(workflow.name)
        if run is None:
            warnings.append(f"workflow missing from recent run list: {workflow.name}")
            continue

        suffix = f"url={run.url}" if run.url else "url=-"
        if run.status != "completed":
            warnings.append(f"{workflow.name}: latest run is {run.status or 'unknown'} ({suffix})")
            continue
        if run.conclusion != "success":
            failures.append(f"{workflow.name}: latest run concluded {run.conclusion or 'unknown'} ({suffix})")
            continue

        current_age = age_hours(run, now=now)
        if workflow.max_age_hours is not None:
            if current_age is None:
                warnings.append(f"{workflow.name}: latest run has no created_at ({suffix})")
                continue
            if current_age > workflow.max_age_hours:
                warnings.append(
                    f"{workflow.name}: latest success is stale "
                    f"age_hours={current_age:.1f} max_age_hours={workflow.max_age_hours:g} ({suffix})"
                )
                continue

        if current_age is None:
            ok.append(f"{workflow.name}: success ({suffix})")
        else:
            ok.append(f"{workflow.name}: success age_hours={current_age:.1f} ({suffix})")

    return ReportResult(ok=ok, warnings=warnings, blockers=[], failures=failures)


def run_live_active_passive(
    *,
    primary_origin: str,
    standby_origin: str,
    runner: Runner | None = None,
) -> ReportResult:
    env = dict(os.environ)
    env.update(
        {
            "CHECK_PUBLIC_READY": "false",
            "PRIMARY_ORIGIN": primary_origin,
            "STANDBY_ORIGIN": standby_origin,
        }
    )
    actual_runner = runner
    if actual_runner is None:
        result = subprocess.run(
            ["bash", "scripts/ha/check_active_passive.sh"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    else:
        result = actual_runner(["bash", "scripts/ha/check_active_passive.sh"], None)

    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    for line in output.splitlines():
        log("live-output", line)

    if result.returncode == 0:
        return ReportResult(
            ok=[f"active/passive direct-origin invariant passed primary={primary_origin} standby={standby_origin}"],
            warnings=[],
            blockers=[],
            failures=[],
        )
    return ReportResult(
        ok=[],
        warnings=[],
        blockers=[],
        failures=[
            f"active/passive direct-origin invariant failed "
            f"primary={primary_origin} standby={standby_origin} exit_code={result.returncode}"
        ],
    )


def external_prereq_result(*, repo: str, require_strict: bool) -> ReportResult:
    metadata = load_metadata(repo=repo)
    ok, warnings, failures = check_metadata(metadata, require_strict=require_strict)
    if require_strict:
        return ReportResult(ok=list(ok), warnings=list(warnings), blockers=[], failures=list(failures))
    return ReportResult(ok=list(ok), warnings=list(warnings), blockers=list(failures), failures=[])


def combine_results(results: Sequence[ReportResult]) -> ReportResult:
    ok: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []
    failures: list[str] = []
    for result in results:
        ok.extend(result.ok)
        warnings.extend(result.warnings)
        blockers.extend(result.blockers)
        failures.extend(result.failures)
    return ReportResult(ok=ok, warnings=warnings, blockers=blockers, failures=failures)


def next_steps_for(result: ReportResult) -> list[str]:
    messages = [*result.failures, *result.blockers, *result.warnings]
    joined = "\n".join(messages)
    next_steps: list[str] = []

    def add_once(message: str) -> None:
        if message not in next_steps:
            next_steps.append(message)

    if result.failures:
        add_once("inspect failed workflow URLs/artifacts before changing API routing or database roles")

    if any(
        key in joined
        for key in (
            "CLOUDFLARE_LB_READ_TOKEN",
            "CLOUDFLARE_ACCOUNT_ID",
            "CLOUDFLARE_ZONE_ID",
        )
    ):
        add_once(
            "create the Cloudflare LB read-only token and zone/account ids, then run "
            "`python3 scripts/ha/apply_cloudflare_lb_github_prerequisites.py --repo mvnby/air-api`"
        )

    if "private PITR R2 credentials are host-local" in joined:
        add_once(
            "install private PostgreSQL PITR R2 credentials on the primary, then run "
            "`ssh mvn-api '/usr/local/sbin/mvn-postgres-pitr-bootstrap verify'`"
        )

    if "POSTGRES_PITR_REQUIRED is not true yet" in joined:
        add_once("run one required PostgreSQL PITR freshness check and physical restore drill before enabling PITR strict mode")

    if any(
        key in joined
        for key in (
            "API_HA_READINESS_STRICT is not true yet",
            "CLOUDFLARE_LB_CONFIG_REQUIRED is not true yet",
            "POSTGRES_PITR_REQUIRED is not true yet",
        )
    ):
        add_once(
            "after Cloudflare LB and PITR proofs pass, enable strict mode with "
            "`python3 scripts/ha/enable_ha_strict_mode.py --repo mvnby/air-api`"
        )

    if any(
        key in joined
        for key in (
            "HA_ALERT_TELEGRAM_BOT_TOKEN",
            "HA_ALERT_TELEGRAM_CHAT_ID",
            "HA_ALERT_TELEGRAM_THREAD_ID",
        )
    ):
        add_once(
            "set HA_ALERT_TELEGRAM_BOT_TOKEN and HA_ALERT_TELEGRAM_CHAT_ID "
            "(optionally HA_ALERT_TELEGRAM_THREAD_ID) to receive owner-visible HA alerts"
        )

    if "live active/passive check skipped" in joined:
        add_once("rerun without --skip-live before failover, promotion, or strict-mode changes")

    return next_steps


def print_result(prefix: str, result: ReportResult) -> None:
    for line in result.ok:
        log(f"{prefix}-ok", line)
    for line in result.warnings:
        log(f"{prefix}-warn", line)
    for line in result.blockers:
        log(f"{prefix}-blocker", line)
    for line in result.failures:
        log(f"{prefix}-fail", line)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report MVN API HA status from current proof surfaces.")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--run-limit", type=int, default=300)
    parser.add_argument("--primary-origin", default=os.environ.get("API_PRIMARY_ORIGIN") or DEFAULT_PRIMARY_ORIGIN)
    parser.add_argument("--standby-origin", default=os.environ.get("API_STANDBY_ORIGIN") or DEFAULT_STANDBY_ORIGIN)
    parser.add_argument("--skip-live", action="store_true", help="Skip direct-origin active/passive curl check.")
    parser.add_argument(
        "--skip-external",
        action="store_true",
        help="Skip GitHub variables/secrets prerequisite metadata check.",
    )
    parser.add_argument(
        "--require-strict",
        action="store_true",
        help="Treat missing external strict-mode prerequisites as hard failures.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    results: list[ReportResult] = []

    try:
        log("info", f"repo={args.repo} branch={args.branch}")
        runs = load_workflow_runs(repo=args.repo, branch=args.branch, limit=max(1, args.run_limit))
        workflow_result = evaluate_workflows(latest_runs_by_workflow(runs))
        print_result("workflow", workflow_result)
        results.append(workflow_result)

        if args.skip_external:
            external_result = ReportResult(ok=[], warnings=["external prerequisite check skipped"], blockers=[], failures=[])
        else:
            external_result = external_prereq_result(repo=args.repo, require_strict=args.require_strict)
        print_result("external", external_result)
        results.append(external_result)

        if args.skip_live:
            live_result = ReportResult(ok=[], warnings=["live active/passive check skipped"], blockers=[], failures=[])
        else:
            live_result = run_live_active_passive(
                primary_origin=args.primary_origin,
                standby_origin=args.standby_origin,
            )
        print_result("live", live_result)
        results.append(live_result)

    except RuntimeError as exc:
        log("fail", str(exc))
        return 2

    combined = combine_results(results)
    log(
        "summary",
        f"status={combined.status} ok={len(combined.ok)} warnings={len(combined.warnings)} "
        f"blockers={len(combined.blockers)} failures={len(combined.failures)}",
    )
    for step in next_steps_for(combined):
        log("next-step", step)
    return 1 if combined.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
