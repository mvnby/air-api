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
    assert _step(job, "Setup Node.js")["with"]["node-version"] == "22"
    build_step = _step(job, "Build Astro site from production API")["run"]
    assert 'printf \'{"sha":"%s"}\\n\'' in build_step
    assert "for attempt in 1 2 3 4 5" in build_step
    assert "sleep $((attempt * 5))" in build_step
    assert "ServerAliveInterval=15" in build_step
    assert "Could not establish API SSH tunnel after 5 attempts" in build_step
    assert "--expected-release" in _step(job, "Validate static release")["run"]
    assert names.index("Deploy Cloudflare Pages canary") < names.index("Deploy atomic VPS fallback")
    assert names.index("Deploy atomic VPS fallback") < names.index("Deploy Cloudflare Pages production")
    assert names.index("Deploy Cloudflare Pages production") < names.index("Smoke stable web endpoints")
    assert _step(job, "Deploy Cloudflare Pages canary")["env"]["CLOUDFLARE_API_TOKEN"] == (
        "${{ secrets.CLOUDFLARE_API_TOKEN_PAGES }}"
    )
    assert 'candidate-${DEPLOY_SHA:0:12}' in _step(job, "Deploy Cloudflare Pages canary")["run"]
    assert "scripts/deploy_web_atomic.sh" in _step(job, "Deploy atomic VPS fallback")["run"]
    stable_smoke = _step(job, "Smoke stable web endpoints")["run"]
    assert '"${base_url}/release.json?sha=${DEPLOY_SHA}"' in stable_smoke
    assert "for attempt in $(seq 1 20)" in stable_smoke
    assert 'sleep 3' in stable_smoke
    assert "did not converge to release" in stable_smoke
    assert '"${SSH_USER_API}@${SSH_HOST_API}"' in stable_smoke
    assert "CLOUDFLARE_PAGES_PROJECT='${CLOUDFLARE_PAGES_PROJECT}' bash -s" in stable_smoke


def test_legacy_web_publishers_are_disconnected_from_active_workflows():
    deploy = _workflow(".github/workflows/deploy.yml")
    rebuild = _workflow(".github/workflows/rebuild-web.yml")
    retired = _step(rebuild["jobs"]["retired"], "Refuse legacy storefront publication")["run"]

    assert "deploy-frontend" not in deploy["jobs"]
    assert "detect-frontend-changes" not in deploy["jobs"]
    assert "mvnby/mvn-web" in retired
    assert "exit 1" in retired

    workflow_text = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in (".github/workflows/deploy.yml", ".github/workflows/rebuild-web.yml")
    )
    assert "uses: ./.github/workflows/deploy-web.yml" not in workflow_text
    assert "rsync -avz --delete" not in workflow_text
