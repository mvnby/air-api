import hashlib
import io
import json
import stat
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.app_static import mount_manager_assets
from routers.manager_spa import create_manager_spa_router
from scripts.ci import retain_manager_assets as history

REPOSITORY = "mvnby/air-api"
CURRENT = "a" * 40
PREVIOUS = "b" * 40
NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)


def bundle(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(history.MANIFEST, json.dumps({"schema": 1, "repository": REPOSITORY, "sha": PREVIOUS}))
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def artifact_api(payload, *, commit=PREVIOUS, run_changes=None, age=1):
    artifact = {
        "id": 17, "name": "manager-dist-23", "expired": False,
        "created_at": (NOW - timedelta(days=age)).isoformat(),
        "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "workflow_run": {"id": 23},
    }
    run = {
        "path": ".github/workflows/ci.yml", "event": "push", "head_branch": "main",
        "status": "completed", "conclusion": "success", "head_sha": commit,
        "repository": {"full_name": REPOSITORY}, "head_repository": {"full_name": REPOSITORY},
        **(run_changes or {}),
    }

    def api(path, *, binary=False):
        if "/actions/artifacts?" in path:
            return {"artifacts": [artifact]}
        if path.endswith("/actions/runs/23"):
            return run
        if "/compare/" in path:
            return {"status": "ahead", "merge_base_commit": {"sha": commit}}
        assert binary and path.endswith("/actions/artifacts/17/zip")
        return payload

    return api


@pytest.fixture
def dist(tmp_path):
    result = tmp_path / "dist"
    (result / "assets").mkdir(parents=True)
    (result / "index.html").write_text('new page <script src="/manager/assets/index-aaaaaaaa.js"></script>')
    (result / "assets/index-aaaaaaaa.js").write_text("new entry")
    return result


@pytest.mark.asyncio
async def test_open_old_tab_loads_previous_chunks_after_image_replacement(dist):
    old_js = "import './shared-12345678.js'; export default 'old screen'"
    payload = bundle({
        "index.html": "old HTML must never replace new HTML",
        "assets/LeadsView-bbbbbbbb.js": old_js,
        "assets/shared-12345678.js": "old shared module",
        "assets/LeadsView-bbbbbbbb.css": ".old{color:blue}",
        "assets/logo-bbbbbbbb.svg": "<svg/>",
        "assets/unhashed.js": "excluded",
        "assets/source-bbbbbbbb.js.map": "excluded source map",
        ".env": "excluded private file",
    })
    result = history.retain_assets(dist, REPOSITORY, CURRENT, api=artifact_api(payload), now=NOW)
    assert result["retained_builds"] == [PREVIOUS]
    assert result["copied_assets"] == 4
    assert not (dist / "assets/unhashed.js").exists()
    assert not (dist / "assets/source-bbbbbbbb.js.map").exists()
    assert not (dist / ".env").exists()
    app = FastAPI()
    mount_manager_assets(app, dist)
    app.include_router(create_manager_spa_router(dist))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for name, content in (("LeadsView-bbbbbbbb.js", old_js), ("shared-12345678.js", "old shared module")):
            response = await client.get(f"/manager/assets/{name}")
            assert response.status_code == 200
            assert response.text == content
            assert "immutable" in response.headers["cache-control"]
        assert (await client.head("/manager/assets/LeadsView-bbbbbbbb.css")).status_code == 200
        assert "new page" in (await client.get("/manager/leads")).text
        assert (await client.get("/manager/assets/index-aaaaaaaa.js")).text == "new entry"


@pytest.mark.parametrize("change", [
    {"event": "pull_request"}, {"head_branch": "feature"}, {"conclusion": "failure"},
    {"status": "in_progress"}, {"path": ".github/workflows/other.yml"},
    {"head_repository": {"full_name": "someone/fork"}}, {"repository": {"full_name": "other/repo"}},
])
def test_history_excludes_untrusted_or_unsuccessful_runs(dist, change):
    payload = bundle({"assets/old-bbbbbbbb.js": "old"})
    result = history.retain_assets(dist, REPOSITORY, CURRENT, api=artifact_api(payload, run_changes=change), now=NOW)
    assert result["copied_assets"] == 0


@pytest.mark.parametrize("commit,age", [(CURRENT, 1), (PREVIOUS, 8)])
def test_current_and_expired_builds_are_not_retained(dist, commit, age):
    payload = bundle({"assets/old-bbbbbbbb.js": "old"})
    assert history.retain_assets(dist, REPOSITORY, CURRENT, api=artifact_api(payload, commit=commit, age=age), now=NOW)["copied_assets"] == 0


def test_future_or_diverged_commit_is_not_retained(dist):
    payload = bundle({"assets/old-bbbbbbbb.js": "old"})
    base_api = artifact_api(payload)

    def api(path, **kwargs):
        return {"status": "behind"} if "/compare/" in path else base_api(path, **kwargs)

    assert history.retain_assets(dist, REPOSITORY, CURRENT, api=api, now=NOW)["copied_assets"] == 0


def test_asset_collision_fails_before_writing_any_history(dist):
    payload = bundle({"assets/old-bbbbbbbb.js": "old", "assets/index-aaaaaaaa.js": "wrong bytes"})
    with pytest.raises(ValueError, match="collision"):
        history.retain_assets(dist, REPOSITORY, CURRENT, api=artifact_api(payload), now=NOW)
    assert not (dist / "assets/old-bbbbbbbb.js").exists()
    assert (dist / "assets/index-aaaaaaaa.js").read_text() == "new entry"


@pytest.mark.parametrize("name", ["../escape.js", "/absolute.js", "assets/../../escape.js", "assets\\escape.js"])
def test_archive_traversal_is_rejected(name):
    payload = bundle({name: "bad", "assets/old-bbbbbbbb.js": "old"})
    with pytest.raises(ValueError, match="Unsafe"):
        history.archive_files(payload, "sha256:" + hashlib.sha256(payload).hexdigest())


def test_symlinks_and_bad_digests_are_rejected():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        link = zipfile.ZipInfo("assets/old-bbbbbbbb.js")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "/private/file")
    payload = output.getvalue()
    with pytest.raises(ValueError, match="Unsafe"):
        history.archive_files(payload, "sha256:" + hashlib.sha256(payload).hexdigest())
    with pytest.raises(ValueError, match="digest mismatch"):
        history.archive_files(payload, "sha256:" + "0" * 64)


def test_size_limits_reject_archive_bombs(monkeypatch):
    payload = bundle({"assets/old-bbbbbbbb.js": "oversized"})
    monkeypatch.setattr(history, "MAX_FILE_BYTES", 2)
    with pytest.raises(ValueError, match="size limit"):
        history.archive_files(payload, "sha256:" + hashlib.sha256(payload).hexdigest())


def test_history_is_bounded_to_five_builds():
    def api(path, **kwargs):
        if "/actions/artifacts?" in path:
            return {"artifacts": [{"name": f"manager-dist-{i}", "workflow_run": {"id": i}, "created_at": NOW.isoformat()} for i in range(1, 10)]}
        if "/actions/runs/" in path:
            commit = str(int(path.rsplit("/", 1)[1])) * 40
            return {"path": ".github/workflows/ci.yml", "event": "push", "head_branch": "main", "status": "completed", "conclusion": "success", "head_sha": commit, "repository": {"full_name": REPOSITORY}, "head_repository": {"full_name": REPOSITORY}}
        return {"status": "ahead", "merge_base_commit": {"sha": path.split("/compare/")[1].split("...")[0]}}

    assert len(history.retained_builds(REPOSITORY, CURRENT, api=api, now=NOW)) == 5


def test_history_api_errors_stop_build_but_expiration_race_is_safe(dist):
    payload = bundle({"assets/old-bbbbbbbb.js": "old"})
    base_api = artifact_api(payload)
    error_status = 403

    def api(path, **kwargs):
        if path.endswith("/zip"):
            raise history.GithubApiError(error_status)
        return base_api(path, **kwargs)

    with pytest.raises(history.GithubApiError):
        history.retain_assets(dist, REPOSITORY, CURRENT, api=api, now=NOW)
    error_status = 410
    assert history.retain_assets(dist, REPOSITORY, CURRENT, api=api, now=NOW)["copied_assets"] == 0


def test_both_image_build_paths_retain_assets_before_docker_build():
    root = Path(__file__).resolve().parents[2]
    for filename, job_name in (("deploy.yml", "deploy-backend"), ("deploy-api-patroni.yml", "build-backend")):
        workflow = yaml.safe_load((root / ".github/workflows" / filename).read_text())
        job = workflow["jobs"][job_name]
        assert job["permissions"]["actions"] == "read"
        steps = job["steps"]
        retain = next(i for i, step in enumerate(steps) if "retain_manager_assets.py" in step.get("run", ""))
        docker = next(i for i, step in enumerate(steps) if "docker/build-push-action@" in step.get("uses", ""))
        assert retain < docker
        assert all("npm run build" not in step.get("run", "") for step in steps)
        assert "--ci-run-id" in steps[retain]["run"]
        assert steps[retain]["env"]["GH_TOKEN"] == "${{ github.token }}"
    workflow = yaml.safe_load((root / ".github/workflows/deploy.yml").read_text())
    caller = workflow["jobs"]["deploy-backend-patroni"]
    assert caller["permissions"]["actions"] == "read"
    assert caller["with"]["ci_run_id"] == "${{ needs.release-gate.outputs.ci_run_id }}"
    ci = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    steps = ci["jobs"]["manager-dist"]["steps"]
    build = next(i for i, step in enumerate(steps) if "npm run build" in step.get("run", ""))
    stamp = next(i for i, step in enumerate(steps) if "--stamp" in step.get("run", ""))
    upload = next(i for i, step in enumerate(steps) if "upload-artifact@" in step.get("uses", ""))
    assert build < stamp < upload
    assert steps[build]["env"]["WEBSITE_URL"] == "https://mvn.by"


def test_release_uses_exact_ci_bytes_and_excludes_private_files(tmp_path):
    payload = bundle({"index.html": "tested HTML", "assets/index-bbbbbbbb.js": "tested module", "assets/kitlane-mark.svg": "<svg/>", ".env": "secret"})
    base_api = artifact_api(payload)
    artifact = {"id": 17, "name": "manager-dist-23", "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}

    def api(path, **kwargs):
        if "/runs/23/artifacts?" in path:
            return {"artifacts": [artifact]}
        return base_api(path, **kwargs)

    dist = tmp_path / "dist"
    history.restore_current_build(dist, REPOSITORY, PREVIOUS, 23, api=api)
    assert (dist / "index.html").read_text() == "tested HTML"
    assert (dist / "assets/index-bbbbbbbb.js").read_text() == "tested module"
    assert (dist / "assets/kitlane-mark.svg").read_text() == "<svg/>"
    assert not (dist / ".env").exists()
    with pytest.raises(ValueError, match="exact SHA"):
        history.restore_current_build(tmp_path / "wrong", REPOSITORY, CURRENT, 23, api=api)


def test_unstamped_legacy_ci_build_is_skipped():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("assets/old-bbbbbbbb.js", "legacy differently configured build")
    payload = output.getvalue()
    assert history.archive_assets(payload, "sha256:" + hashlib.sha256(payload).hexdigest(), REPOSITORY, PREVIOUS) == {}
