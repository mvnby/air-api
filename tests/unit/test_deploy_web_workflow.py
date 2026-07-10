from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _workflow(path: str) -> dict:
    return yaml.load((REPO_ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(job: dict, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_reusable_web_release_promotes_one_immutable_artifact_in_safe_order():
    workflow = _workflow(".github/workflows/deploy-web.yml")
    job = workflow["jobs"]["production-web"]
    names = [step.get("name") for step in job["steps"]]

    assert workflow["on"]["workflow_call"]["inputs"]["deploy_sha"]["required"] == "true"
    assert job["environment"] == "production-web"
    assert _step(job, "Checkout immutable release")["with"]["ref"] == "${{ inputs.deploy_sha }}"
    assert 'printf \'{"sha":"%s"}\\n\'' in _step(job, "Build Astro site from production API")["run"]
    assert "--expected-release" in _step(job, "Validate static release")["run"]
    assert names.index("Deploy Cloudflare Pages canary") < names.index("Deploy atomic VPS fallback")
    assert names.index("Deploy atomic VPS fallback") < names.index("Deploy Cloudflare Pages production")
    assert names.index("Deploy Cloudflare Pages production") < names.index("Smoke stable web endpoints")
    assert _step(job, "Deploy Cloudflare Pages canary")["env"]["CLOUDFLARE_API_TOKEN"] == (
        "${{ secrets.CLOUDFLARE_API_TOKEN_PAGES }}"
    )
    assert 'candidate-${DEPLOY_SHA:0:12}' in _step(job, "Deploy Cloudflare Pages canary")["run"]
    assert "scripts/deploy_web_atomic.sh" in _step(job, "Deploy atomic VPS fallback")["run"]
    assert '"${base_url}/release.json?sha=${DEPLOY_SHA}"' in _step(job, "Smoke stable web endpoints")["run"]


def test_release_and_manual_rebuild_call_the_same_web_workflow():
    deploy = _workflow(".github/workflows/deploy.yml")
    rebuild = _workflow(".github/workflows/rebuild-web.yml")
    automatic = deploy["jobs"]["deploy-frontend"]
    manual = rebuild["jobs"]["rebuild"]

    assert automatic["uses"] == "./.github/workflows/deploy-web.yml"
    assert automatic["with"]["deploy_sha"] == "${{ needs.release-gate.outputs.deploy_sha }}"
    assert manual["uses"] == "./.github/workflows/deploy-web.yml"
    assert manual["with"]["deploy_sha"] == "${{ github.sha }}"
    assert manual["needs"] == "main-branch-guard"
    assert rebuild["jobs"]["callback"]["if"] == "${{ always() }}"

    workflow_text = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in (".github/workflows/deploy.yml", ".github/workflows/rebuild-web.yml")
    )
    assert "rsync -avz --delete" not in workflow_text
