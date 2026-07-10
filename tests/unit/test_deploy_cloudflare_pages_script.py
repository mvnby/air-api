import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/deploy_cloudflare_pages.sh"
SHA = "b" * 40


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_pages_deploy_uses_pinned_wrangler_and_smokes_returned_url(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    _executable(
        fake_bin / "fake-npx",
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "$COMMAND_LOG"
printf 'Deployment complete! Take a peek over at https://abc123.mvn-by.pages.dev\n'
""",
    )
    _executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
printf 'curl %s\n' "$*" >> "$COMMAND_LOG"
if [[ "$*" == *release.json* ]]; then
  printf '{"sha":"%s"}\n' "$EXPECTED_SHA"
fi
""",
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("index", encoding="utf-8")
    (dist / "release.json").write_text(json.dumps({"sha": SHA}), encoding="utf-8")
    github_output = tmp_path / "github-output"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "COMMAND_LOG": str(command_log),
            "EXPECTED_SHA": SHA,
            "CLOUDFLARE_API_TOKEN": "test-token",
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_PAGES_PROJECT": "mvn-by",
            "CLOUDFLARE_PAGES_BRANCH": "candidate-123",
            "PAGES_COMMIT_SHA": SHA,
            "PAGES_DIST_DIR": str(dist),
            "WRANGLER_BIN": "fake-npx",
            "PAGES_DEPLOY_OUTPUT_FILE": str(tmp_path / "deploy.log"),
            "GITHUB_OUTPUT": str(github_output),
        }
    )

    result = subprocess.run(["bash", str(SCRIPT)], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    calls = command_log.read_text(encoding="utf-8")
    assert "--yes wrangler@4.110.0 pages deploy" in calls
    assert "--branch candidate-123" in calls
    assert f"--commit-hash {SHA}" in calls
    assert "https://abc123.mvn-by.pages.dev/" in calls
    assert "deployment_url=https://abc123.mvn-by.pages.dev" in github_output.read_text(encoding="utf-8")


def test_pages_deploy_rejects_mutable_commit_identifier(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("index", encoding="utf-8")
    (dist / "release.json").write_text(json.dumps({"sha": SHA}), encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "CLOUDFLARE_API_TOKEN": "test-token",
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_PAGES_BRANCH": "main",
            "PAGES_COMMIT_SHA": "main",
            "PAGES_DIST_DIR": str(dist),
        }
    )

    result = subprocess.run(["bash", str(SCRIPT)], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 1
    assert "full Git SHA" in result.stdout


def test_pages_deploy_supports_pinned_pnpm_runner(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    _executable(
        fake_bin / "fake-pnpm",
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "$COMMAND_LOG"
printf 'Deployment complete: https://pnpm123.mvn-by.pages.dev\n'
""",
    )
    _executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
if [[ "$*" == *release.json* ]]; then
  printf '{"sha":"%s"}\n' "$EXPECTED_SHA"
fi
""",
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("index", encoding="utf-8")
    (dist / "release.json").write_text(json.dumps({"sha": SHA}), encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "COMMAND_LOG": str(command_log),
            "EXPECTED_SHA": SHA,
            "CLOUDFLARE_API_TOKEN": "test-token",
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_PAGES_BRANCH": "candidate-pnpm",
            "PAGES_COMMIT_SHA": SHA,
            "PAGES_DIST_DIR": str(dist),
            "WRANGLER_BIN": "fake-pnpm",
            "WRANGLER_RUNNER": "pnpm",
            "PAGES_DEPLOY_OUTPUT_FILE": str(tmp_path / "deploy.log"),
        }
    )

    result = subprocess.run(["bash", str(SCRIPT)], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert "dlx wrangler@4.110.0 pages deploy" in command_log.read_text(encoding="utf-8")
