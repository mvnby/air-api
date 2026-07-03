from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/check-cloudflare-lb-config.yml")


def test_cloudflare_lb_workflow_has_strict_required_gate():
    workflow = WORKFLOW_PATH.read_text()

    assert "required:" in workflow
    assert "CF_LB_CONFIG_REQUIRED:" in workflow
    assert "CLOUDFLARE_LB_CONFIG_REQUIRED" in workflow
    assert "CF_LB_SKIP_IF_MISSING_CREDENTIALS=false" in workflow
    assert "CF_LB_SKIP_IF_MISSING_CREDENTIALS=true" in workflow
    assert 'CF_LB_SKIP_IF_MISSING_CREDENTIALS: "true"' not in workflow
