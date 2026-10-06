#!/usr/bin/env python3
"""Authorize an exact-SHA release from trusted main-push CI job results."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


APPLICATION_JOBS = {
    "manager-dist", "manager", "backend-contracts", "pytest-unit", "pytest-integration",
}
DOCS_JOBS = {"manager-dist", "manager", "backend-contracts", "pytest-skipped"}


def deployment_needed(run: dict, pages: list[dict], repository: str, sha: str) -> bool:
    """Return False only for a verified documentation-only run; reject ambiguity."""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("invalid release SHA")
    expected = {
        "event": "push", "path": ".github/workflows/ci.yml", "head_branch": "main",
        "head_sha": sha, "status": "completed", "conclusion": "success",
    }
    for key, value in expected.items():
        if run.get(key) != value:
            raise ValueError(f"untrusted or unsuccessful CI: {key}")
    for key in ("repository", "head_repository"):
        if (run.get(key) or {}).get("full_name") != repository:
            raise ValueError(f"CI repository mismatch: {key}")

    required = APPLICATION_JOBS | DOCS_JOBS | {"test", "changes"}
    jobs = {}
    for page in pages:
        for job in page["jobs"]:
            name = job["name"]
            if name not in required:
                continue
            if name in jobs:
                raise ValueError(f"ambiguous CI job: {name}")
            if job.get("head_sha") != sha or job.get("status") != "completed":
                raise ValueError(f"unfinished or wrong-SHA CI job: {name}")
            jobs[name] = job.get("conclusion")
    if jobs.get("test") != "success":
        raise ValueError("required test gate did not succeed")
    # Older full runs predate the classifier. They remain valid for manual replay;
    # skipping application checks always requires the new classification gate.
    if "changes" in jobs and jobs["changes"] != "success":
        raise ValueError("change classification did not succeed")
    if "pytest-skipped" not in jobs and all(jobs.get(name) == "success" for name in APPLICATION_JOBS):
        return True
    # Job-level conditions run before matrix expansion. The unexpanded matrix
    # uses the explicit name fallback from ci.yml on the documentation route.
    skipped_names = set(jobs) - {"test", "changes"}
    if (jobs.get("changes") == "success"
        and skipped_names in (DOCS_JOBS, APPLICATION_JOBS)
        and all(jobs[name] == "skipped" for name in skipped_names)):
        return False
    raise ValueError("missing, failed or inconsistently skipped application checks")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-json", required=True)
    parser.add_argument("--jobs-json", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("--github-output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()
    try:
        needed = deployment_needed(
            json.loads(Path(args.run_json).read_text()),
            json.loads(Path(args.jobs_json).read_text()),
            args.repository, args.sha,
        )
        if args.manual and not needed:
            raise ValueError("manual release requires full application CI for the exact SHA")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"Release refused: {exc}")
        return 1
    result = "full application CI passed" if needed else "documentation only; deployment skipped"
    with Path(args.github_output).open("a") as output:
        output.write(f"deployment_needed={str(needed).lower()}\n")
    with Path(args.summary).open("a") as summary:
        summary.write(f"## Release gate\n\n- Tested SHA: `{args.sha}`\n- Result: {result}\n")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
