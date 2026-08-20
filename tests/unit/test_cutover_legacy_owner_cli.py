from __future__ import annotations

from io import BytesIO

import pytest

from scripts.cutover_legacy_owner import (
    build_parser,
    read_credential_input,
    read_execution_input,
    validate_args,
)


def test_cli_exposes_reviewed_actions_without_password_argument() -> None:
    parser = build_parser()
    assert parser.parse_args(["plan"]).action == "plan"
    assert parser.parse_args(["verify"]).action == "verify"
    assert parser.parse_args(["rollback", "--plan-token", "token"]).action == "rollback"
    with pytest.raises(SystemExit):
        parser.parse_args(["execute", "--password", "forbidden"])


def test_execute_stdin_requires_exact_plan_and_one_time_credential() -> None:
    assert read_execution_input(
        BytesIO(b'{"plan_token":"signed","new_password":"long-password"}'),
        require_password=True,
    ) == ("signed", "long-password")
    with pytest.raises(ValueError, match="unexpected schema"):
        read_execution_input(
            BytesIO(b'{"plan_token":"signed","password":"no"}'),
            require_password=True,
        )


def test_verify_credential_stdin_accepts_only_one_time_credential() -> None:
    assert read_credential_input(
        BytesIO(b'{"new_password":"long-password"}')
    ) == "long-password"
    with pytest.raises(ValueError, match="unexpected schema"):
        read_credential_input(
            BytesIO(b'{"new_password":"long-password","plan_token":"no"}')
        )


def test_rollback_requires_fresh_token() -> None:
    parser = build_parser()
    args = parser.parse_args(["rollback"])
    with pytest.raises(SystemExit):
        validate_args(args, parser)
