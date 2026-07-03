#!/usr/bin/env python3
"""Apply Cloudflare Load Balancer audit prerequisites to GitHub.

The Cloudflare API token is intentionally passed to `gh secret set` through
stdin, not as a command-line argument, so it does not appear in process args.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence


DEFAULT_REPO = "mvnby/air-api"
DEFAULT_REF = "main"
WORKFLOW = "check-cloudflare-lb-config.yml"
DEFAULT_TOKEN_ENV = "CLOUDFLARE_LB_READ_TOKEN"
TOKEN_FALLBACK_ENVS = ("CLOUDFLARE_API_TOKEN_LB_AUDIT",)

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


def _parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, raw_value = line.split("=", 1)
    key = key.strip().removeprefix("export ").strip()
    if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        return None
    raw_value = raw_value.strip()
    if raw_value and raw_value[0] in {"'", '"'}:
        try:
            parts = shlex.split(f"{key}={raw_value}", posix=True)
        except ValueError:
            parts = []
        if parts and "=" in parts[0]:
            return key, parts[0].split("=", 1)[1]
    if " #" in raw_value:
        raw_value = raw_value.split(" #", 1)[0].rstrip()
    return key, raw_value


def load_env_file(path: Path, *, allowed_names: set[str]) -> None:
    if not path.exists():
        raise RuntimeError(f"env file not found: {path}")
    loaded = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in allowed_names:
            continue
        if key not in os.environ:
            os.environ[key] = value
            loaded += 1
    log("ok", f"loaded env file: {path} keys={loaded}")


def _first_env_value(names: Sequence[str]) -> tuple[str, str]:
    for name in names:
        value = env_value(name)
        if value:
            return value, name
    return "", names[0] if names else ""


def collect_inputs(
    *,
    token_env: str,
    zone_id_env: str,
    account_id_env: str,
    token_fallback_envs: Sequence[str] = TOKEN_FALLBACK_ENVS,
) -> tuple[str, str, str, str]:
    token, token_source = _first_env_value((token_env, *token_fallback_envs))
    zone_id = env_value(zone_id_env)
    account_id = env_value(account_id_env)
    token_label = token_env
    if token_fallback_envs:
        token_label = f"{token_env} (or {'/'.join(token_fallback_envs)})"
    missing = []
    if not token:
        missing.append(token_label)
    missing.extend(
        env_name
        for env_name, value in ((zone_id_env, zone_id), (account_id_env, account_id))
        if not value
    )
    if missing:
        raise RuntimeError("missing required environment variables: " + ", ".join(missing))
    return token, zone_id, account_id, token_source


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


def parse_run_id_optional(output: str) -> str | None:
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


def run_cloudflare_required_workflow(
    *,
    repo: str,
    ref: str,
    wait: bool,
    runner: Runner | None = None,
) -> str:
    started_after = datetime.now(timezone.utc) - timedelta(seconds=10)
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
    run_id = parse_run_id_optional(output)
    if not run_id:
        run_id = find_recent_workflow_run_id(
            repo=repo,
            ref=ref,
            workflow=WORKFLOW,
            started_after=started_after,
            runner=runner,
        )
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
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV)
    parser.add_argument("--zone-id-env", default="CLOUDFLARE_ZONE_ID")
    parser.add_argument("--account-id-env", default="CLOUDFLARE_ACCOUNT_ID")
    parser.add_argument(
        "--env-file",
        default=os.environ.get("HA_ENV_FILE") or "",
        help="Optional dotenv-style file to load before reading Cloudflare inputs.",
    )
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
        if args.env_file:
            load_env_file(
                Path(args.env_file),
                allowed_names={
                    args.token_env,
                    *TOKEN_FALLBACK_ENVS,
                    args.zone_id_env,
                    args.account_id_env,
                },
            )
        token, zone_id, account_id, token_source = collect_inputs(
            token_env=args.token_env,
            zone_id_env=args.zone_id_env,
            account_id_env=args.account_id_env,
        )
        log("info", f"repo={args.repo} ref={args.ref}")
        log("info", f"using token from ${token_source}; value will not be printed")
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
