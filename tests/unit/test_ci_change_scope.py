import subprocess
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts.ci.change_scope import inspect_changes, main, previous_push_verified


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def repository(tmp_path: Path, monkeypatch) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "ci@example.invalid")
    git(repo, "config", "user.name", "CI test")
    (repo / "base.txt").write_text("base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    monkeypatch.chdir(repo)
    return repo, base


def commit(repo: Path, message: str = "change") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.mark.parametrize("verified", [True, False])
def test_docs_push_cannot_bypass_pending_predecessor_code(tmp_path, monkeypatch, verified):
    repo, _ = repository(tmp_path, monkeypatch)
    (repo / "app.py").write_text("new_feature = True\n")
    code_sha = commit(repo, "feature still in CI")
    (repo / "README.md").write_text("# Documentation\n")
    docs_sha = commit(repo, "documentation after feature")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/api")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")

    def verify(repository_name, branch, sha):
        assert (repository_name, branch, sha) == ("example/api", "main", code_sha)
        return verified

    monkeypatch.setattr("scripts.ci.change_scope.previous_push_verified", verify)
    manifest = tmp_path / "scope.json"
    output = tmp_path / "github-output"
    monkeypatch.setattr(sys, "argv", ["change_scope.py", "--base", code_sha, "--head", docs_sha,
                                     "--verify-previous-push", "--output-json", str(manifest),
                                     "--github-output", str(output)])
    assert main() == 0
    result = json.loads(manifest.read_text())
    assert result["docs_only"] is verified
    assert result["markdown_paths"] == ["README.md"]
    assert output.read_text() == f"docs_only={str(verified).lower()}\n"


@pytest.mark.parametrize("branch", ["main", "master"])
def test_previous_push_lookup_requires_exact_successful_commit(monkeypatch, branch):
    sha = "a" * 40
    def run(args, **kwargs):
        assert args[args.index("--repo") + 1] == "example/api"
        assert args[args.index("--branch") + 1] == branch
        assert args[args.index("--commit") + 1] == sha
        assert args[args.index("--workflow") + 1] == "ci.yml"
        assert args[args.index("--event") + 1] == "push"
        assert kwargs["check"] and kwargs["timeout"] == 30
        return SimpleNamespace(stdout=json.dumps([{"headSha": sha, "headBranch": branch,
                                                 "event": "push", "status": "completed", "conclusion": "success"}]))
    monkeypatch.setattr(subprocess, "run", run)
    assert previous_push_verified("example/api", branch, sha)


@pytest.mark.parametrize("response", [
    "[]", "null", "{}", "invalid json", '[{"headSha":"wrong"}]',
    json.dumps([{"headSha":"a" * 40, "headBranch":"main", "event":"pull_request", "status":"completed", "conclusion":"success"}]),
    json.dumps([{"headSha":"a" * 40, "headBranch":"main", "event":"push", "status":"in_progress", "conclusion":None}]),
])
def test_unconfirmed_predecessor_requires_full_ci(monkeypatch, response):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=response))
    assert not previous_push_verified("example/api", "main", "a" * 40)


@pytest.mark.parametrize("error", [OSError("missing gh"), subprocess.CalledProcessError(1, "gh"), subprocess.TimeoutExpired("gh", 30)])
def test_lookup_failure_requires_full_ci(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(subprocess, "run", fail)
    assert not previous_push_verified("example/api", "main", "a" * 40)


def test_docs_allowlist_includes_requested_paths(tmp_path, monkeypatch):
    repo, base = repository(tmp_path, monkeypatch)
    for path in ("docs/top.md", "AGENTS.md", "README.md", ".github/copilot-instructions.md", ".github/pull_request_template.md"):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Notes\n")
    head = commit(repo)
    result = inspect_changes(base, head)
    assert result["docs_only"] is True
    assert result["reason"] == "all changes are allowlisted Markdown files"
    assert len(result["markdown_paths"]) == 5


def test_mixed_unknown_missing_zero_and_empty_diffs_fail_closed(tmp_path, monkeypatch):
    repo, base = repository(tmp_path, monkeypatch)
    (repo / "docs/guide.md").parent.mkdir()
    (repo / "docs/guide.md").write_text("# Guide\n")
    (repo / "app.py").write_text("pass\n")
    head = commit(repo)
    assert inspect_changes(base, head)["docs_only"] is False
    assert inspect_changes(base, base)["reason"] == "empty diff"
    assert inspect_changes(None, head)["docs_only"] is False
    assert inspect_changes("0" * 40, head)["docs_only"] is False


def test_deletions_renames_symlinks_and_executable_markdown_fail_closed(tmp_path, monkeypatch):
    repo, _ = repository(tmp_path, monkeypatch)
    (repo / "docs/old.md").parent.mkdir()
    (repo / "docs/old.md").write_text("# old\n")
    base = commit(repo, "add old")
    (repo / "docs/old.md").rename(repo / "docs/new.md")
    renamed = commit(repo, "rename")
    assert inspect_changes(base, renamed)["docs_only"] is False

    delete_base = renamed
    (repo / "docs/new.md").unlink()
    deleted = commit(repo, "delete")
    assert inspect_changes(delete_base, deleted)["docs_only"] is False

    (repo / "docs/link.md").symlink_to("../base.txt")
    link = commit(repo, "symlink")
    assert inspect_changes(deleted, link)["docs_only"] is False

    (repo / "docs/run.md").write_text("# executable\n")
    (repo / "docs/run.md").chmod(0o755)
    executable = commit(repo, "executable markdown")
    assert inspect_changes(link, executable)["docs_only"] is False


def test_large_unicode_and_spaced_diff_has_no_path_limit(tmp_path, monkeypatch):
    repo, base = repository(tmp_path, monkeypatch)
    for index in range(325):
        folder = repo / "docs"
        folder.mkdir(exist_ok=True)
        (folder / f"guide {index} — café.md").write_text("# Guide\n")
    head = commit(repo, "many docs")
    result = inspect_changes(base, head)
    assert result["docs_only"] is True
    assert len(result["changes"]) == 325
    assert any("café" in item["path"] for item in result["changes"])


def test_mode_change_to_executable_is_not_docs_only(tmp_path, monkeypatch):
    repo, base = repository(tmp_path, monkeypatch)
    path = repo / "docs/guide.md"
    path.parent.mkdir()
    path.write_text("# Guide\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "add doc")
    prior = git(repo, "rev-parse", "HEAD")
    path.chmod(0o755)
    head = commit(repo, "change mode")
    assert inspect_changes(prior, head)["docs_only"] is False


def test_executable_to_regular_markdown_is_not_docs_only(tmp_path, monkeypatch):
    repo, _ = repository(tmp_path, monkeypatch)
    path = repo / "docs/guide.md"
    path.parent.mkdir()
    path.write_text("# Guide\n")
    path.chmod(0o755)
    base = commit(repo, "add executable doc")
    path.chmod(0o644)
    path.write_text("# Updated guide\n")
    head = commit(repo, "make regular")
    assert inspect_changes(base, head)["docs_only"] is False


def test_runtime_file_renamed_into_docs_is_not_docs_only(tmp_path, monkeypatch):
    repo, _ = repository(tmp_path, monkeypatch)
    (repo / "module.py").write_text("VALUE = 1\n")
    base = commit(repo, "add runtime file")
    (repo / "docs").mkdir()
    (repo / "module.py").rename(repo / "docs/module.md")
    head = commit(repo, "rename into docs")
    result = inspect_changes(base, head)
    assert result["docs_only"] is False
    assert {change["status"] for change in result["changes"]} == {"A", "D"}


def test_pull_request_merge_base_ignores_unrelated_base_branch_commit(tmp_path, monkeypatch):
    repo, common = repository(tmp_path, monkeypatch)
    git(repo, "branch", "feature")
    (repo / "runtime.py").write_text("VALUE = 1\n")
    base = commit(repo, "base branch runtime change")
    git(repo, "checkout", "-q", "feature")
    (repo / "docs/guide.md").parent.mkdir()
    (repo / "docs/guide.md").write_text("# Guide\n")
    head = commit(repo, "feature docs change")
    assert inspect_changes(base, head)["docs_only"] is False
    result = inspect_changes(base, head, merge_base=True)
    assert result["docs_only"] is True
    assert result["base"] == common


def test_cli_writes_json_and_github_output(tmp_path, monkeypatch):
    repo, base = repository(tmp_path, monkeypatch)
    (repo / "docs/guide.md").parent.mkdir()
    (repo / "docs/guide.md").write_text("# Guide\n")
    head = commit(repo)
    json_path = tmp_path / "scope.json"
    github_output = tmp_path / "github-output"
    script = Path(__file__).resolve().parents[2] / "scripts/ci/change_scope.py"
    subprocess.run(
        [sys.executable, str(script), "--base", base, "--head", head,
         "--output-json", str(json_path), "--github-output", str(github_output)],
        check=True, capture_output=True, text=True,
    )
    assert '"docs_only": true' in json_path.read_text()
    assert github_output.read_text() == "docs_only=true\n"
