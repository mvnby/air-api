"""Carry five recent, successful main CI builds' hashed Manager assets into an image.

Only public content-addressed assets are copied, never historical index.html or
application data. The original CI artifacts are not cumulative, so history stays
bounded. GitHub CLI handles authenticated API redirects without exposing tokens.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

ASSET_NAME = re.compile(r"[A-Za-z0-9_.-]+-[A-Za-z0-9_-]{8}\.(?:js|css|svg|png|jpe?g|webp|avif|gif|ico|woff2?|ttf|eot)\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
HISTORY_BUILDS = 5
HISTORY_DAYS = 7
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
MANIFEST = "manager-release.json"


class GithubApiError(RuntimeError):
    def __init__(self, status: int | None):
        super().__init__(f"GitHub asset history API failed (status={status or 'unknown'})")
        self.status = status


def github_api(path: str, *, binary: bool = False):
    result = subprocess.run(
        ["gh", "api", "--hostname", "github.com", "-H", "X-GitHub-Api-Version: 2022-11-28", path],
        capture_output=True, timeout=60, check=False,
    )
    if result.returncode:
        match = re.search(rb"HTTP (\d{3})", result.stderr)
        raise GithubApiError(int(match[1]) if match else None)
    if binary:
        if len(result.stdout) > MAX_ARCHIVE_BYTES:
            raise ValueError("Manager asset archive exceeds compressed size limit")
        return result.stdout
    return json.loads(result.stdout)


def archive_files(payload: bytes, digest: str | None) -> dict[str, bytes]:
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("Manager asset archive exceeds compressed size limit")
    if not digest or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Manager asset archive has no valid SHA-256 digest")
    if hashlib.sha256(payload).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError("Manager asset archive digest mismatch")
    files = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if len(entries) > 4096 or sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES:
            raise ValueError("Manager asset archive exceeds expanded size limit")
        seen = set()
        for item in entries:
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in item.filename
                    or item.filename in seen or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError("Unsafe Manager asset archive entry")
            seen.add(item.filename)
            if item.is_dir():
                continue
            if item.file_size > MAX_FILE_BYTES:
                raise ValueError("Manager asset archive entry exceeds size limit")
            files[item.filename] = archive.read(item)
    return files


def manifest_matches(files, repository, commit):
    # Older CI artifacts were rebuilt with different production environment
    # inputs. Only the new exact-artifact release contract is safe to retain.
    if MANIFEST not in files:
        return False
    if json.loads(files[MANIFEST]) != {"schema": 1, "repository": repository, "sha": commit}:
        raise ValueError("Manager release manifest mismatch")
    return True


def archive_assets(payload: bytes, digest: str | None, repository: str, commit: str) -> dict[str, bytes]:
    files = archive_files(payload, digest)
    if not manifest_matches(files, repository, commit):
        return {}
    assets = {PurePosixPath(name).name: content for name, content in files.items()
              if len(PurePosixPath(name).parts) == 2 and name.startswith("assets/")
              and ASSET_NAME.fullmatch(PurePosixPath(name).name)}
    if not assets:
        raise ValueError("Manager CI artifact contains no hashed assets")
    return assets


def trusted_run(run, repository):
    return (run.get("path") == ".github/workflows/ci.yml" and run.get("event") == "push"
            and run.get("head_branch") == "main" and run.get("conclusion") == "success"
            and run.get("status") == "completed" and SHA.fullmatch(run.get("head_sha", ""))
            and run.get("repository", {}).get("full_name") == repository
            and run.get("head_repository", {}).get("full_name") == repository)


def restore_current_build(dist, repository, deploy_sha, run_id, *, api=github_api):
    run = api(f"repos/{repository}/actions/runs/{run_id}")
    if not trusted_run(run, repository) or run["head_sha"] != deploy_sha:
        raise ValueError("Manager release requires successful main CI for exact SHA")
    artifacts = api(f"repos/{repository}/actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    matches = [item for item in artifacts if item["name"] == f"manager-dist-{run_id}" and not item.get("expired")]
    if len(matches) != 1:
        raise ValueError("Exact Manager CI build artifact is unavailable")
    artifact = matches[0]
    files = archive_files(api(f"repos/{repository}/actions/artifacts/{int(artifact['id'])}/zip", binary=True), artifact.get("digest"))
    if not manifest_matches(files, repository, deploy_sha) or "index.html" not in files:
        raise ValueError("Exact Manager release manifest or index is missing")
    if dist.exists() and any(dist.iterdir()):
        raise ValueError("Refusing to replace a nonempty Manager build")
    for name, content in files.items():
        path = PurePosixPath(name)
        if name not in {"index.html", MANIFEST} and not (
                path.parts[0] == "assets" and path.suffix.lower() in {
                    ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".eot"}):
            continue
        destination = dist / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def retained_builds(repository: str, deploy_sha: str, *, api=github_api, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=HISTORY_DAYS)
    selected = []
    seen_commits = {deploy_sha}
    # Bounded discovery includes unrelated artifacts; a week of normal CI is
    # well below 500. An empty history bootstraps safely on the first release.
    for page in range(1, 6):
        artifacts = api(f"repos/{repository}/actions/artifacts?per_page=100&page={page}")["artifacts"]
        for artifact in artifacts:
            if artifact.get("expired"):
                continue
            created = datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00"))
            if created < cutoff:
                continue
            run_id = artifact.get("workflow_run", {}).get("id")
            if not isinstance(run_id, int) or artifact["name"] != f"manager-dist-{run_id}":
                continue
            run = api(f"repos/{repository}/actions/runs/{run_id}")
            commit = run.get("head_sha", "")
            if not trusted_run(run, repository) or commit in seen_commits:
                continue
            comparison = api(f"repos/{repository}/compare/{commit}...{deploy_sha}")
            if comparison.get("status") != "ahead" or comparison.get("merge_base_commit", {}).get("sha") != commit:
                continue
            selected.append((commit, artifact))
            seen_commits.add(commit)
            if len(selected) == HISTORY_BUILDS:
                return selected
        if len(artifacts) < 100:
            break
    return selected


def retain_assets(dist: Path, repository: str, deploy_sha: str, *, api=github_api, now=None):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not SHA.fullmatch(deploy_sha):
        raise ValueError("Expected an exact repository and immutable deployment SHA")
    target = dist / "assets"
    if not (dist / "index.html").is_file() or not target.is_dir() or target.is_symlink():
        raise ValueError("Current Manager build is missing")
    # Validate all history before writing; conflicting names must never replace
    # the current build or silently mix different modules behind immutable URLs.
    pending = {}
    commits = []
    for commit, artifact in retained_builds(repository, deploy_sha, api=api, now=now):
        try:
            payload = api(f"repos/{repository}/actions/artifacts/{int(artifact['id'])}/zip", binary=True)
        except GithubApiError as error:
            if error.status in {404, 410}:  # Artifact expired during discovery.
                continue
            raise
        assets = archive_assets(payload, artifact.get("digest"), repository, commit)
        if not assets:
            continue
        for name, content in assets.items():
            current = target / name
            if current.is_symlink() or (current.exists() and current.read_bytes() != content):
                raise ValueError("Manager immutable asset collision")
            if name in pending and pending[name] != content:
                raise ValueError("Manager historical asset collision")
            if not current.exists():
                pending[name] = content
        commits.append(commit)
    for name, content in pending.items():
        (target / name).write_bytes(content)
    return {"retained_builds": commits, "copied_assets": len(pending), "history_days": HISTORY_DAYS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("manager_frontend/dist"))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--deploy-sha", required=True)
    parser.add_argument("--ci-run-id", type=int)
    parser.add_argument("--stamp", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository) or not SHA.fullmatch(args.deploy_sha):
        parser.error("Expected an exact repository and immutable SHA")
    if args.stamp:
        (args.dist / MANIFEST).write_text(json.dumps({"schema": 1, "repository": args.repository, "sha": args.deploy_sha}))
        return
    if not args.ci_run_id or args.ci_run_id <= 0:
        parser.error("--ci-run-id is required for an exact-artifact release")
    restore_current_build(args.dist, args.repository, args.deploy_sha, args.ci_run_id)
    print(json.dumps(retain_assets(args.dist, args.repository, args.deploy_sha)))


if __name__ == "__main__":
    main()
