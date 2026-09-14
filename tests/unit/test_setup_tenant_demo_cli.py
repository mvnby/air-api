import pytest

from scripts.setup_tenant_demo import parse_args


def test_cli_defaults_to_read_only_plan():
    args = parse_args(["--tenant-id", "35", "--storefront-id", "36"])
    assert args.action == "plan"
    assert args.plan_token is None


def test_cli_requires_plan_token_only_for_execute():
    with pytest.raises(SystemExit):
        parse_args(["execute", "--tenant-id", "35", "--storefront-id", "36"])
    with pytest.raises(SystemExit):
        parse_args(
            [
                "plan",
                "--tenant-id",
                "35",
                "--storefront-id",
                "36",
                "--plan-token",
                "unexpected",
            ]
        )
