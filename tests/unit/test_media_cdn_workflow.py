from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _workflow(path: str) -> dict:
    return yaml.load((REPO_ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(workflow: dict, step_name: str) -> dict:
    return next(step for step in workflow["jobs"]["check"]["steps"] if step.get("name") == step_name)


def test_media_cdn_workflow_keeps_public_and_db_backed_checks():
    workflow = _workflow(".github/workflows/check-media-cdn.yml")
    dispatch_inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    public_step = _step(workflow, "Run media CDN check")
    ssh_step = _step(workflow, "Setup API SSH Key")
    db_step = _step(workflow, "Run DB-backed media CDN check")
    summary_step = _step(workflow, "Write Summary")
    artifact_step = _step(workflow, "Upload media CDN log")
    expected_source_thresholds = "product_image_variant=1,media_asset=1,order_technical_meta=1"

    assert dispatch_inputs["min_db_cdn_urls"]["default"] == "3"
    assert dispatch_inputs["min_db_cdn_urls_by_source"]["default"] == expected_source_thresholds
    assert "scripts/check_media_cdn_public.py" in public_step["run"]
    assert "secrets.SSH_HOST_API" in ssh_step["env"]["SSH_HOST_API"]
    assert "secrets.SSH_USER_API" in ssh_step["env"]["SSH_USER_API"]
    assert "secrets.SSH_KEY" in ssh_step["env"]["SSH_KEY"]
    assert "scripts/check_media_cdn_db_urls.py" in db_step["run"]
    assert "--min-db-cdn-urls" in db_step["run"]
    assert "--min-db-cdn-urls-by-source" in db_step["run"]
    assert (
        db_step["env"]["MIN_DB_CDN_URLS_BY_SOURCE"]
        == "${{ github.event_name == 'workflow_dispatch' && "
        f"inputs.min_db_cdn_urls_by_source || '{expected_source_thresholds}' }}}}"
    )
    assert "tee -a media-cdn-check.log" in db_step["run"]
    assert "min_db_cdn_urls:" in summary_step["run"]
    assert "min_db_cdn_urls_by_source:" in summary_step["run"]
    assert artifact_step["if"] == "always()"
    assert artifact_step["with"]["path"] == "media-cdn-check.log"
