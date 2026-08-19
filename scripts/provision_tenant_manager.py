"""Plan and execute a least-privilege tenant manager provisioning request."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

sys.path.append(".")

from services.tenant_manager_provisioning_service import (  # noqa: E402
    TenantManagerProvisioningBlockedError,
    TenantManagerProvisioningRequest,
    TenantManagerProvisioningService,
)
from services.storefront_onboarding_state import (  # noqa: E402
    StorefrontOnboardingBlockedError,
)


_ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_EXECUTION_INPUT_BYTES = 16_384


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Provision one tenant-scoped manager. Plan is read-only; execute "
            "requires a fresh plan token and one secret input source."
        )
    )
    parser.add_argument("action", choices=("plan", "execute"))
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--storefront-slug", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--phone", required=True)
    parser.add_argument("--plan-token")
    parser.add_argument(
        "--execution-json-stdin",
        action="store_true",
        help=(
            "Read an exact JSON object containing plan_token and password from "
            "stdin. This keeps both values out of process arguments and the "
            "environment for reviewed automation."
        ),
    )
    password_source = parser.add_mutually_exclusive_group()
    password_source.add_argument("--password-file", type=Path)
    password_source.add_argument("--password-env", metavar="VARIABLE")
    password_source.add_argument("--password-stdin", action="store_true")
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    sources = password_source_count(args)
    if args.action == "plan":
        if args.plan_token or sources or args.execution_json_stdin:
            parser.error(
                "plan does not accept a plan token or execution input source"
            )
        return
    if args.execution_json_stdin:
        if args.plan_token or sources:
            parser.error(
                "--execution-json-stdin cannot be combined with a plan token "
                "or another password source"
            )
        return
    if not args.plan_token:
        parser.error("execute requires --plan-token from a fresh plan")
    if sources > 1:
        parser.error("execute accepts at most one password source")
    if args.password_env and not _ENVIRONMENT_NAME_PATTERN.fullmatch(args.password_env):
        parser.error("--password-env must name one environment variable")


def request_from_args(args: argparse.Namespace) -> TenantManagerProvisioningRequest:
    return TenantManagerProvisioningRequest.normalize(
        tenant_slug=args.tenant_slug,
        storefront_slug=args.storefront_slug,
        display_name=args.display_name,
        username=args.username,
        phone=args.phone,
    )


def read_password(args: argparse.Namespace) -> str:
    if args.password_env:
        value = os.environ.get(args.password_env)
        if value is None:
            raise ValueError("Password environment variable is not set")
        return value
    if args.password_file:
        try:
            metadata = args.password_file.stat()
        except OSError as exc:
            raise ValueError("Password file cannot be read") from exc
        mode = stat.S_IMODE(metadata.st_mode)
        if not stat.S_ISREG(metadata.st_mode) or mode not in {0o400, 0o600}:
            raise ValueError("Password file must be a regular file with mode 0400 or 0600")
        try:
            value = args.password_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError("Password file cannot be read as UTF-8") from exc
    else:
        value = sys.stdin.read()
    if value.endswith("\r\n"):
        return value[:-2]
    if value.endswith("\n"):
        return value[:-1]
    return value


def read_execution_input(stream: Any | None = None) -> tuple[str, str]:
    source = stream if stream is not None else sys.stdin.buffer
    payload = source.read(_MAX_EXECUTION_INPUT_BYTES + 1)
    if len(payload) > _MAX_EXECUTION_INPUT_BYTES:
        raise ValueError("Execution input is too large")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Execution input must be valid UTF-8 JSON") from exc
    if not isinstance(decoded, dict) or set(decoded) != {"plan_token", "password"}:
        raise ValueError(
            "Execution input must contain exactly plan_token and password"
        )
    plan_token = decoded["plan_token"]
    password = decoded["password"]
    if not isinstance(plan_token, str) or not plan_token or len(plan_token) > 4096:
        raise ValueError("Execution input plan token is invalid")
    if not isinstance(password, str) or not password:
        raise ValueError("Execution input password is invalid")
    return plan_token, password


async def run(args: argparse.Namespace) -> dict[str, Any]:
    from core.database import async_session_maker

    request = request_from_args(args)
    execution_input = read_execution_input() if args.execution_json_stdin else None
    async with async_session_maker() as session:
        try:
            if args.action == "plan":
                result = await TenantManagerProvisioningService.plan(
                    session, request=request
                )
                result["reviewed_execute_command"] = reviewed_command(args, result)
                return result
            result = await TenantManagerProvisioningService.execute(
                session,
                request=request,
                password=(
                    execution_input[1]
                    if execution_input is not None
                    else (read_password(args) if password_source_count(args) else None)
                ),
                plan_token=(
                    execution_input[0]
                    if execution_input is not None
                    else args.plan_token
                ),
            )
            await session.commit()
            return result
        except Exception:
            if args.action == "execute":
                await session.rollback()
            raise


def reviewed_command(args: argparse.Namespace, result: dict[str, Any]) -> str | None:
    if not result["ready"]:
        return None
    target = result["target"]
    command = [
        "python3",
        "scripts/provision_tenant_manager.py",
        "execute",
        "--tenant-slug",
        target["tenant_slug"],
        "--storefront-slug",
        target["storefront_slug"],
        "--display-name",
        target["display_name"],
        "--username",
        target["username"],
        "--phone",
        target["phone"],
        "--plan-token",
        result["plan_token"],
    ]
    if result["changes"]:
        command.append("--password-stdin")
    return shlex.join(command)


def password_source_count(args: argparse.Namespace) -> int:
    return sum(
        bool(value)
        for value in (args.password_file, args.password_env, args.password_stdin)
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    try:
        result = asyncio.run(run(args))
    except (
        TenantManagerProvisioningBlockedError,
        StorefrontOnboardingBlockedError,
        ValueError,
    ) as exc:
        print(f"tenant_manager_provisioning status=blocked error={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except IntegrityError as exc:
        print(
            "tenant_manager_provisioning status=blocked "
            "error=database state changed concurrently",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    except Exception as exc:
        print(
            "tenant_manager_provisioning status=error "
            "error=unexpected transaction failure",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    if not result.get("ready", False):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
