from __future__ import annotations

import os

import pytest

from scripts.provision_tenant_manager import (
    build_parser,
    password_source_count,
    read_password,
    reviewed_command,
    validate_args,
)
from services.tenant_manager_provisioning_service import TenantManagerProvisioningService


def _base_arguments(action: str) -> list[str]:
    return [
        action,
        "--tenant-slug",
        "polotsk",
        "--storefront-slug",
        "main",
        "--display-name",
        "Андрей",
        "--username",
        "andrey-polotsk",
        "--phone",
        "+375297146293",
    ]


def test_plan_rejects_password_source_and_execute_keeps_noop_passwordless() -> None:
    parser = build_parser()
    plan = parser.parse_args(_base_arguments("plan"))
    validate_args(plan, parser)

    with pytest.raises(SystemExit):
        validate_args(
            parser.parse_args(_base_arguments("plan") + ["--password-stdin"]),
            parser,
        )

    execute = parser.parse_args(
        _base_arguments("execute") + ["--plan-token", "reviewed-token"]
    )
    validate_args(execute, parser)
    assert password_source_count(execute) == 0


def test_password_sources_never_require_a_command_line_secret(tmp_path, monkeypatch) -> None:
    parser = build_parser()
    password_file = tmp_path / "password"
    password_file.write_text("manager-password-2026\n", encoding="utf-8")
    password_file.chmod(0o600)
    from_file = parser.parse_args(
        _base_arguments("execute")
        + ["--plan-token", "token", "--password-file", str(password_file)]
    )
    validate_args(from_file, parser)
    assert read_password(from_file) == "manager-password-2026"

    monkeypatch.setenv("MANAGER_PASSWORD", "manager-password-2026")
    from_environment = parser.parse_args(
        _base_arguments("execute")
        + ["--plan-token", "token", "--password-env", "MANAGER_PASSWORD"]
    )
    assert read_password(from_environment) == "manager-password-2026"
    assert "manager-password-2026" not in " ".join(from_environment.__dict__.keys())
    os.environ.pop("MANAGER_PASSWORD")


def test_world_readable_password_file_is_rejected(tmp_path) -> None:
    parser = build_parser()
    password_file = tmp_path / "password"
    password_file.write_text("manager-password-2026", encoding="utf-8")
    password_file.chmod(0o644)
    args = parser.parse_args(
        _base_arguments("execute")
        + ["--plan-token", "token", "--password-file", str(password_file)]
    )

    with pytest.raises(ValueError, match="0400 or 0600"):
        read_password(args)


def test_password_file_accepts_exactly_reviewed_private_modes(tmp_path) -> None:
    parser = build_parser()
    password_file = tmp_path / "password"
    password_file.write_text("manager-password-2026", encoding="utf-8")
    password_file.chmod(0o400)
    args = parser.parse_args(
        _base_arguments("execute")
        + ["--plan-token", "token", "--password-file", str(password_file)]
    )

    assert read_password(args) == "manager-password-2026"


def test_password_byte_limit_matches_bcrypt_with_unicode() -> None:
    valid_unicode = "Ж" * 30

    TenantManagerProvisioningService._validate_password(valid_unicode)
    TenantManagerProvisioningService._validate_password("a" * 72)
    with pytest.raises(ValueError, match="72 UTF-8 bytes"):
        TenantManagerProvisioningService._validate_password("Ж" * 37)
    with pytest.raises(ValueError, match="72 UTF-8 bytes"):
        TenantManagerProvisioningService._validate_password("a" * 73)


def test_reviewed_command_uses_stdin_only_when_plan_creates_a_user() -> None:
    parser = build_parser()
    args = parser.parse_args(_base_arguments("plan"))
    target = {
        "tenant_slug": "polotsk",
        "storefront_slug": "main",
        "display_name": "Андрей",
        "username": "andrey-polotsk",
        "phone": "+375297146293",
    }

    creation = reviewed_command(
        args,
        {"ready": True, "target": target, "plan_token": "token", "changes": ["create_staff_user"]},
    )
    no_op = reviewed_command(
        args,
        {"ready": True, "target": target, "plan_token": "token", "changes": []},
    )

    assert "--password-stdin" in creation
    assert "--password-stdin" not in no_op
