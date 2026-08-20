from __future__ import annotations

from io import BytesIO

import pytest

from scripts.cutover_legacy_owner import build_parser, read_execution_input, validate_args


def test_cli_exposes_reviewed_actions_without_password_input() -> None:
    parser = build_parser()
    assert parser.parse_args(["plan"]).action == "plan"
    assert parser.parse_args(["verify"]).action == "verify"
    assert parser.parse_args(["rollback", "--plan-token", "token"]).action == "rollback"
    with pytest.raises(SystemExit):
        parser.parse_args(["execute", "--password", "forbidden"])


def test_execution_stdin_accepts_only_plan_token() -> None:
    assert read_execution_input(BytesIO(b'{"plan_token":"signed"}')) == "signed"
    with pytest.raises(ValueError, match="exactly plan_token"):
        read_execution_input(BytesIO(b'{"plan_token":"signed","password":"no"}'))


def test_rollback_requires_fresh_token() -> None:
    parser = build_parser()
    args = parser.parse_args(["rollback"])
    with pytest.raises(SystemExit):
        validate_args(args, parser)
