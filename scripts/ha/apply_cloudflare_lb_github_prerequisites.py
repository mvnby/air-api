#!/usr/bin/env python3
"""Apply Cloudflare Load Balancer audit prerequisites to GitHub.

The Cloudflare API token is intentionally passed to `gh secret set` through
stdin, not as a command-line argument, so it does not appear in process args.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence


DEFAULT_REPO = "mvnby/air-api"
DEFAULT_REF = "main"
WORKFLOW = "check-cloudflare-lb-config.yml"

Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]


def log(stage: str, message: str) -> None:
    print(f"[ha-cloudflare-setup][{stage}] {message}")


def _run_subprocess(args: Sequence[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def run_checked(args: Sequence[str], *, stdin: str | None = None, runner: Runner | None = None) -> str:
    actual_runner = runner or _run_subprocess
    result = actual_runner(args, stdin)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(output or f"command failed: {' '.join(args)}")
    return result.stdout.strip()


def env_value(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def collect_inputs(*, token_env: str, zone_id_env: str, account_id_env: str) -> tuple[str, str, str]:
    values = (
        env_value(token_env),
        env_value(zone_id_env),
        env_value(account_id_env),
    )
    missing = [
        env_name
        for env_name, value in zip((token_env, zone_id_env, account_id_env), values, strict=True)
        if not value
    ]
    if missing:
        raise RuntimeError("missing required environment variables: " + ", ".join(missing))
    return values


def set_secret(repo: str, name: str, value: str, *, runner: Runner | None = None) -> None:
    run_checked(["gh", "secret", "set", name, "--repo", repo], stdin=f"{value}\n", runner=runner)
    log("ok", f"GitHub secret set: {name}")


def set_variable(repo: str, name: str, value: str, *, runner: Runner | None = None) -> None:
    run_checked(["gh", "variable", "set", name, "--repo", repo], stdin=f"{value}\n", runner=runner)
    log("ok", f"GitHub variable set: {name}")


def run_external_prereq_check(repo: str, *, runner: Runner | None = None) -> None:
    script = Path(__file__).with_name("check_ha_external_prerequisites.py")
    output = run_checked([sys.executable, str(script), "--repo", repo], runner=runner)
    if output:
        print(output)


def parse_run_id(output: str) -> str:
    match = re.search(r"/actions/runs/([0-9]+)", output)
    if not match:
        raise RuntimeError(f"could not parse GitHub Actions run id from: {output!r}")
    return match.group(1)


def run_cloudflare_required_workflow(
    *,
    repo: str,
    ref: str,
    wait: bool,
    runner: Runner | None = None,
) -> str:
    output = run_checked(
        [
            "gh",
            "workflow",
            "run",
            WORKFLOW,
            "--repo",
            repo,
            "--ref",
            ref,
            "-f",
            "required=true",
        ],
        runner=runner,
    )
    run_id = parse_run_id(output)
    log("ok", f"started Cloudflare LB required audit: {output}")
    if wait:
        run_checked(
            ["gh", "run", "watch", run_id, "--repo", repo, "--exit-status", "--interval", "10"],
            runner=runner,
        )
        log("ok", f"Cloudflare LB required audit passed: {run_id}")
    return run_id


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set GitHub Cloudflare LB audit prerequisites and run the required audit."
    )
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO)
    parser.add_argument("--ref", default=DEFAULT_REF)
    parser.add_argument("--token-env", default="CLOUDFLARE_LB_READ_TOKEN")
    parser.add_argument("--zone-id-env", default="CLOUDFLARE_ZONE_ID")
    parser.add_argument("--account-id-env", default="CLOUDFLARE_ACCOUNT_ID")
    parser.add_argument(
        "--mark-required",
        action="store_true",
        help="Set CLOUDFLARE_LB_CONFIG_REQUIRED=true after the required audit passes.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Start the required workflow but do not wait for it to finish.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate local inputs and print intended actions without writing GitHub metadata.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        token, zone_id, account_id = collect_inputs(
            token_env=args.token_env,
            zone_id_env=args.zone_id_env,
            account_id_env=args.account_id_env,
        )
        log("info", f"repo={args.repo} ref={args.ref}")
        log("info", f"using token from ${args.token_env}; value will not be printed")
        if args.mark_required and args.no_wait:
            raise RuntimeError("--mark-required requires waiting for the required audit to pass")

        if args.dry_run:
            log("dry-run", "would set GitHub secret CLOUDFLARE_LB_READ_TOKEN")
            log("dry-run", "would set GitHub variables CLOUDFLARE_ZONE_ID and CLOUDFLARE_ACCOUNT_ID")
            log("dry-run", f"would run {WORKFLOW} with required=true")
            if args.mark_required:
                log("dry-run", "would set CLOUDFLARE_LB_CONFIG_REQUIRED=true after audit success")
            return 0

        set_secret(args.repo, "CLOUDFLARE_LB_READ_TOKEN", token)
        set_variable(args.repo, "CLOUDFLARE_ZONE_ID", zone_id)
        set_variable(args.repo, "CLOUDFLARE_ACCOUNT_ID", account_id)
        run_external_prereq_check(args.repo)
        run_cloudflare_required_workflow(repo=args.repo, ref=args.ref, wait=not args.no_wait)

        if args.mark_required:
            set_variable(args.repo, "CLOUDFLARE_LB_CONFIG_REQUIRED", "true")
            run_external_prereq_check(args.repo)
        return 0
    except RuntimeError as exc:
        log("fail", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
