#!/usr/bin/env python3
"""Check GitHub-side external prerequisites for MVN API HA strict mode.

This script intentionally checks only metadata: variable names/values and secret
names. It never reads or prints secret values.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Sequence


DEFAULT_REPO = "mvnby/air-api"

REQUIRED_SECRETS = {
    "CLOUDFLARE_LB_READ_TOKEN": "Cloudflare read-only token for Load Balancer config audit",
}

OPTIONAL_SECRETS = {
    "HA_ALERT_TELEGRAM_BOT_TOKEN": "Telegram bot token for owner-visible HA failure alerts",
    "HA_ALERT_TELEGRAM_CHAT_ID": "Telegram chat id for owner-visible HA failure alerts",
}

REQUIRED_VARIABLES = {
    "API_HA_READINESS_STRICT": "Controls whether the rollup HA audit treats soft blockers as failures",
    "CLOUDFLARE_ACCOUNT_ID": "Cloudflare account id for Load Balancer pools/monitors",
    "CLOUDFLARE_LB_CONFIG_REQUIRED": "Controls whether the Cloudflare LB audit is strict",
    "CLOUDFLARE_ZONE_ID": "Cloudflare zone id for api.mvn.by load balancer lookup",
    "POSTGRES_PITR_MAX_BASEBACKUP_AGE_HOURS": "Maximum accepted private PITR basebackup age",
    "POSTGRES_PITR_MAX_WAL_AGE_MINUTES": "Maximum accepted private PITR WAL age",
    "POSTGRES_PITR_REQUIRED": "Controls whether PITR archive/timer/remote checks are strict",
}

STRICT_TRUE_VARIABLES = (
    "API_HA_READINESS_STRICT",
    "CLOUDFLARE_LB_CONFIG_REQUIRED",
    "POSTGRES_PITR_REQUIRED",
)


@dataclass(frozen=True)
class GithubMetadata:
    variables: dict[str, str]
    secrets: set[str]


def _run_gh_json(args: Sequence[str]) -> object:
    result = subprocess.run(
        ["gh", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "gh command failed"
        raise RuntimeError(message)
    return json.loads(result.stdout or "[]")


def load_github_metadata(repo: str) -> GithubMetadata:
    raw_vars = _run_gh_json(["variable", "list", "--repo", repo, "--json", "name,value"])
    raw_secrets = _run_gh_json(["secret", "list", "--repo", repo, "--json", "name"])
    if not isinstance(raw_vars, list) or not isinstance(raw_secrets, list):
        raise RuntimeError("unexpected gh JSON response")

    variables = {
        str(item.get("name")): str(item.get("value") or "")
        for item in raw_vars
        if isinstance(item, dict) and item.get("name")
    }
    secrets = {
        str(item.get("name"))
        for item in raw_secrets
        if isinstance(item, dict) and item.get("name")
    }
    return GithubMetadata(variables=variables, secrets=secrets)


def load_env_metadata() -> GithubMetadata:
    """Load prerequisite metadata from process env without printing secrets.

    GitHub Actions' default token can run workflows and read workflow history,
    but it is not a good fit for listing repository secret metadata. Scheduled
    HA reports pass the relevant secret names as env vars and this loader only
    records whether each value is non-empty.
    """

    variables = {
        name: os.getenv(name, "").strip()
        for name in REQUIRED_VARIABLES
        if os.getenv(name, "").strip()
    }
    secret_names = set(REQUIRED_SECRETS) | set(OPTIONAL_SECRETS)
    secrets = {name for name in secret_names if os.getenv(name, "").strip()}
    return GithubMetadata(variables=variables, secrets=secrets)


def load_metadata(*, repo: str, source: str | None = None) -> GithubMetadata:
    metadata_source = (source or os.getenv("HA_EXTERNAL_METADATA_SOURCE") or "github").strip().lower()
    if metadata_source == "github":
        return load_github_metadata(repo)
    if metadata_source == "env":
        return load_env_metadata()
    raise RuntimeError("HA_EXTERNAL_METADATA_SOURCE must be 'github' or 'env'")


def is_true(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def check_metadata(metadata: GithubMetadata, *, require_strict: bool) -> tuple[list[str], list[str], list[str]]:
    ok: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []

    for name, description in sorted(REQUIRED_SECRETS.items()):
        if name in metadata.secrets:
            ok.append(f"secret present: {name}")
        else:
            failures.append(f"missing GitHub secret {name}: {description}")

    for name, description in sorted(OPTIONAL_SECRETS.items()):
        if name in metadata.secrets:
            ok.append(f"optional secret present: {name}")
        else:
            warnings.append(f"missing optional GitHub secret {name}: {description}")

    for name, description in sorted(REQUIRED_VARIABLES.items()):
        value = metadata.variables.get(name)
        if value:
            ok.append(f"variable present: {name}")
        else:
            failures.append(f"missing GitHub variable {name}: {description}")

    for name in STRICT_TRUE_VARIABLES:
        value = metadata.variables.get(name)
        if value is None:
            continue
        if is_true(value):
            ok.append(f"strict variable enabled: {name}")
        elif require_strict:
            failures.append(f"{name} must be true before strict HA mode")
        else:
            warnings.append(f"{name} is not true yet")

    warnings.append(
        "private PITR R2 credentials are host-local; verify with "
        "`ssh mvn-api '/usr/local/sbin/mvn-postgres-pitr-bootstrap verify'` "
        "after bucket credentials are installed"
    )
    return ok, warnings, failures


def print_report(*, repo: str, ok: Sequence[str], warnings: Sequence[str], failures: Sequence[str]) -> None:
    print(f"[ha-external][info] repo={repo}")
    for line in ok:
        print(f"[ha-external][ok] {line}")
    for line in warnings:
        print(f"[ha-external][warn] {line}")
    for line in failures:
        print(f"[ha-external][fail] {line}")
    status = "failed" if failures else "passed"
    print(
        f"[ha-external][summary] status={status} "
        f"failures={len(failures)} warnings={len(warnings)}"
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check GitHub vars/secrets needed before MVN API HA strict mode."
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO,
        help=f"GitHub repository in owner/name form. Default: {DEFAULT_REPO}",
    )
    parser.add_argument(
        "--require-strict",
        action="store_true",
        help="Fail unless strict-mode variables are already true.",
    )
    parser.add_argument(
        "--metadata-source",
        choices=("github", "env"),
        default=os.environ.get("HA_EXTERNAL_METADATA_SOURCE") or "github",
        help="Where to read prerequisite metadata from. Default: github.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        metadata = load_metadata(repo=args.repo, source=args.metadata_source)
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"[ha-external][fail] {exc}", file=sys.stderr)
        return 2

    ok, warnings, failures = check_metadata(metadata, require_strict=args.require_strict)
    print_report(repo=args.repo, ok=ok, warnings=warnings, failures=failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
