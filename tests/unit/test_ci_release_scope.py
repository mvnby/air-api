import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.ci.release_scope import APPLICATION_JOBS, DOCS_JOBS, deployment_needed


SHA = "a" * 40
REPOSITORY = "mvnby/air-api"


def evidence(docs_only=False):
    run = {"event": "push", "path": ".github/workflows/ci.yml", "head_branch": "main",
           "head_sha": SHA, "status": "completed", "conclusion": "success",
           "repository": {"full_name": REPOSITORY}, "head_repository": {"full_name": REPOSITORY}}
    jobs = [{"name": name, "head_sha": SHA, "status": "completed", "conclusion": state}
            for names, state in [({"changes", "test"}, "success"),
                                 (DOCS_JOBS if docs_only else APPLICATION_JOBS,
                                  "skipped" if docs_only else "success")]
            for name in sorted(names)]
    return run, [{"jobs": jobs}]


def test_full_and_docs_only_release_decisions():
    assert deployment_needed(*evidence(), REPOSITORY, SHA) is True
    assert deployment_needed(*evidence(True), REPOSITORY, SHA) is False


@pytest.mark.parametrize("conclusion,accepted", [("skipped", True), ("success", False), ("failure", False)])
def test_actual_github_unexpanded_matrix_name(conclusion, accepted):
    run, pages = evidence(True)
    job = next(job for job in pages[0]["jobs"] if job["name"] == "pytest-skipped")
    # Actual Jobs API response from docs-only run 37527932570, not an evaluated expression.
    job["name"] = "pytest-${{ (matrix.suite || 'skipped') }}"
    job["conclusion"] = conclusion
    if accepted:
        assert deployment_needed(run, pages, REPOSITORY, SHA) is False
    else:
        with pytest.raises(ValueError):
            deployment_needed(run, pages, REPOSITORY, SHA)


def test_full_legacy_run_can_be_replayed_but_cannot_skip_checks():
    run, pages = evidence()
    pages[0]["jobs"] = [job for job in pages[0]["jobs"] if job["name"] != "changes"]
    assert deployment_needed(run, pages, REPOSITORY, SHA) is True
    for job in pages[0]["jobs"]:
        if job["name"] != "test":
            job["conclusion"] = "skipped"
    with pytest.raises(ValueError):
        deployment_needed(run, pages, REPOSITORY, SHA)


@pytest.mark.parametrize("field,value", [
    ("event", "pull_request"), ("head_branch", "feature"), ("head_sha", "b" * 40),
    ("status", "in_progress"), ("conclusion", "failure"), ("conclusion", "cancelled"),
    ("path", ".github/workflows/other.yml"),
    ("repository", {"full_name": "other/repo"}),
    ("head_repository", {"full_name": "fork/air-api"}), ("head_repository", None),
])
def test_rejects_untrusted_or_incomplete_run(field, value):
    run, pages = evidence()
    run[field] = value
    with pytest.raises(ValueError):
        deployment_needed(run, pages, REPOSITORY, SHA)


@pytest.mark.parametrize("docs_only", [True, False])
@pytest.mark.parametrize("mutation", ["missing", "failed", "cancelled", "duplicate", "wrong_sha", "unfinished"])
def test_every_required_job_is_checked(docs_only, mutation):
    run, original = evidence(docs_only)
    for index in range(len(original[0]["jobs"])):
        pages = deepcopy(original)
        job = pages[0]["jobs"][index]
        # Full legacy runs intentionally need no classification job.
        if not docs_only and mutation == "missing" and job["name"] == "changes":
            continue
        if mutation == "missing":
            pages[0]["jobs"].pop(index)
        elif mutation == "duplicate":
            pages.append({"jobs": [job]})
        elif mutation == "wrong_sha":
            job["head_sha"] = "b" * 40
        elif mutation == "unfinished":
            job["status"] = "in_progress"
        else:
            job["conclusion"] = "failure" if mutation == "failed" else "cancelled"
        with pytest.raises(ValueError):
            deployment_needed(run, pages, REPOSITORY, SHA)


def test_rejects_mixed_success_and_skip_and_accepts_paginated_evidence():
    run, pages = evidence()
    pages[0]["jobs"].append({"name": "unrelated", "conclusion": "success"})
    pages = [{"jobs": pages[0]["jobs"][:3]}, {"jobs": pages[0]["jobs"][3:]}]
    assert deployment_needed(run, pages, REPOSITORY, SHA) is True
    next(job for page in pages for job in page["jobs"] if job["name"] == "pytest-unit")["conclusion"] = "skipped"
    with pytest.raises(ValueError):
        deployment_needed(run, pages, REPOSITORY, SHA)


@pytest.mark.parametrize("manual,passed", [(False, True), (True, False)])
def test_cli_writes_decision_only_after_validation(tmp_path, manual, passed):
    run, pages = evidence(True)
    (tmp_path / "run.json").write_text(json.dumps(run))
    (tmp_path / "jobs.json").write_text(json.dumps(pages))
    output, summary = tmp_path / "output", tmp_path / "summary"
    args = [sys.executable, str(Path("scripts/ci/release_scope.py").resolve()),
            "--run-json", str(tmp_path / "run.json"), "--jobs-json", str(tmp_path / "jobs.json"),
            "--repository", REPOSITORY, "--sha", SHA, "--github-output", str(output), "--summary", str(summary)]
    result = subprocess.run(args + (["--manual"] if manual else []), capture_output=True, text=True)
    assert (result.returncode == 0) is passed, result.stdout
    if passed:
        assert output.read_text() == "deployment_needed=false\n"
        assert "deployment skipped" in summary.read_text()
    else:
        assert not output.exists()
