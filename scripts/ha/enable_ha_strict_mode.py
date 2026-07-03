#!/usr/bin/env python3
"""Enable MVN API HA strict mode only after proof workflows pass.

The helper intentionally sets GitHub strict-mode variables only after the
Cloudflare LB audit, PostgreSQL PITR freshness check, PITR restore drill, and
strict HA readiness audit have all passed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence


DEFAULT_REPO = "mvnby/air-api"
DEFAULT_REF = "main"

STRICT_VARIABLES = (
    "CLOUDFLARE_LB_CONFIG_REQUIRED",
    "POSTGRES_PITR_REQUIRED",
    "API_HA_READINESS_STRICT",
)

Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class WorkflowProof:
    workflow: str
    description: str
    fields: Mapping[str, str]


PROOF_WORKFLOWS = (
    WorkflowProof(
        workflow="check-cloudflare-lb-config.yml",
        description="Cloudflare Load Balancer required config audit",
        fields={"required": "true"},
    ),
    WorkflowProof(
        workflow="check-postgres-pitr.yml",
        description="PostgreSQL PITR required freshness/status check",
        fields={"required": "true"},
    ),
    WorkflowProof(
        workflow="postgres-pitr-restore-drill.yml",
        description="PostgreSQL PITR physical restore drill",
        fields={"required": "true"},
    ),
    WorkflowProof(
        workflow="check-api-ha-readiness.yml",
        description="whole-system HA readiness audit in strict mode",
        fields={"strict": "true"},
    ),
)


def log(stage: str, message: str) -> None:
    print(f"[ha-strict-enable][{stage}] {message}")


def _run_subprocess(args: Sequence[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def run_checked(
    args: Sequence[str],
    *,
    stdin: str | None = None,
    runner: Runner | None = None,
    print_stdout: bool = True,
) -> str:
    actual_runner = runner or _run_subprocess
    result = actual_runner(args, stdin)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(output or f"command failed: {' '.join(args)}")
    output = result.stdout.strip()
    if print_stdout and output:
        print(output)
    return output


def parse_run_id(output: str) -> str | None:
    match = re.search(r"/actions/runs/([0-9]+)", output)
    if match:
        return match.group(1)
    return None


def parse_github_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def find_recent_workflow_run_id(
    *,
    repo: str,
    ref: str,
    workflow: str,
    started_after: datetime,
    runner: Runner | None = None,
) -> str:
    output = run_checked(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--branch",
            ref,
            "--event",
            "workflow_dispatch",
            "--json",
            "databaseId,createdAt,url",
            "--limit",
            "10",
        ],
        runner=runner,
        print_stdout=False,
    )
    try:
        runs = json.loads(output or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"could not parse gh run list output for {workflow}: {output!r}") from exc

    candidates: list[tuple[datetime, str]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        created_at = parse_github_time(str(run.get("createdAt") or ""))
        run_id = str(run.get("databaseId") or "")
        if created_at and run_id and created_at >= started_after:
            candidates.append((created_at, run_id))

    if not candidates:
        raise RuntimeError(
            f"could not find a recent workflow_dispatch run for {workflow}; "
            "rerun or inspect GitHub Actions manually"
        )

    candidates.sort(reverse=True)
    return candidates[0][1]


def trigger_and_wait_workflow(
    proof: WorkflowProof,
    *,
    repo: str,
    ref: str,
    runner: Runner | None = None,
) -> str:
    log("start", proof.description)
    started_after = datetime.now(timezone.utc) - timedelta(seconds=10)
    args = ["gh", "workflow", "run", proof.workflow, "--repo", repo, "--ref", ref]
    for key, value in proof.fields.items():
        args.extend(["-f", f"{key}={value}"])

    output = run_checked(args, runner=runner)
    run_id = parse_run_id(output)
    if not run_id:
        run_id = find_recent_workflow_run_id(
            repo=repo,
            ref=ref,
            workflow=proof.workflow,
            started_after=started_after,
            runner=runner,
        )

    run_checked(
        ["gh", "run", "watch", run_id, "--repo", repo, "--exit-status", "--interval", "10"],
        runner=runner,
    )
    log("ok", f"{proof.workflow} passed: {run_id}")
    return run_id


def set_variable(repo: str, name: str, value: str, *, runner: Runner | None = None) -> None:
    run_checked(["gh", "variable", "set", name, "--repo", repo], stdin=f"{value}\n", runner=runner)
    log("ok", f"GitHub variable set: {name}={value}")


def run_external_prereq_check(repo: str, *, require_strict: bool, runner: Runner | None = None) -> None:
    script = Path(__file__).with_name("check_ha_external_prerequisites.py")
    args = [sys.executable, str(script), "--repo", repo]
    if require_strict:
        args.append("--require-strict")
    run_checked(args, runner=runner)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run MVN HA proof workflows and enable GitHub strict-mode variables only after they pass."
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--ref", default=DEFAULT_REF)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the proof sequence and variables that would be set without running workflows.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        log("info", f"repo={args.repo} ref={args.ref}")
        if args.dry_run:
            log("dry-run", "would verify non-strict external prerequisites")
            for proof in PROOF_WORKFLOWS:
                fields = " ".join(f"{key}={value}" for key, value in proof.fields.items())
                log("dry-run", f"would run and wait for {proof.workflow} {fields}")
            for name in STRICT_VARIABLES:
                log("dry-run", f"would set GitHub variable {name}=true")
            log("dry-run", "would verify strict external prerequisites")
            return 0

        run_external_prereq_check(args.repo, require_strict=False)
        for proof in PROOF_WORKFLOWS:
            trigger_and_wait_workflow(proof, repo=args.repo, ref=args.ref)

        for name in STRICT_VARIABLES:
            set_variable(args.repo, name, "true")

        run_external_prereq_check(args.repo, require_strict=True)
        log("ok", "strict HA mode is enabled")
        return 0
    except RuntimeError as exc:
        log("fail", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
