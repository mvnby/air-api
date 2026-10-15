import pytest

from scripts.setup_tenant_training import parse_args
from scripts.bootstrap_private_training import parse_args as parse_bootstrap_args
from services.tenant_demo_setup_service import TenantDemoSetupPlanToken
from services.tenant_training_setup_service import TenantTrainingPlanToken


TARGET = ["--tenant-id", "38", "--storefront-id", "39", "--tenant-slug", "training-kitlane"]


def test_defaults_to_read_only_and_binds_exact_target():
    args = parse_args(TARGET)
    assert args.action == "plan" and args.plan_token is None
    assert args.tenant_slug == "training-kitlane"


def test_execute_requires_token_and_plan_rejects_it():
    with pytest.raises(SystemExit):
        parse_args(["execute", *TARGET])
    with pytest.raises(SystemExit):
        parse_args([*TARGET, "--plan-token", "unexpected"])


def test_shared_demo_plan_token_cannot_authorize_training():
    token = TenantDemoSetupPlanToken.issue(plan_digest="a" * 64)
    with pytest.raises(RuntimeError):
        TenantTrainingPlanToken.verify(token)


def test_private_bootstrap_defaults_to_read_only_and_needs_exactly_two_products():
    args = parse_bootstrap_args(["--product-id", "33", "--product-id", "39"])
    assert args.action == "plan" and args.plan_token is None
    for values in (["33"], ["33", "33"], ["0", "39"]):
        with pytest.raises(SystemExit):
            parse_bootstrap_args([part for value in values for part in ("--product-id", value)])


def test_private_bootstrap_execute_requires_reviewed_token():
    with pytest.raises(SystemExit):
        parse_bootstrap_args(["execute", "--product-id", "33", "--product-id", "39"])
