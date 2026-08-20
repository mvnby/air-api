"""Plan or execute the legacy env-owner compatibility cutover."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy.exc import IntegrityError

sys.path.append(".")

from services.legacy_owner_cutover_service import (  # noqa: E402
    LegacyOwnerCutoverBlockedError,
    LegacyOwnerCutoverService,
)


MAX_EXECUTION_INPUT_BYTES = 4 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cut over the canonical legacy env owner. Plan is read-only; "
            "execute requires its exact fresh signed token."
        )
    )
    parser.add_argument("action", choices=("plan", "execute", "verify", "rollback"))
    parser.add_argument(
        "--for-action",
        choices=("cutover", "rollback"),
        default="cutover",
        help="Bind a plan token to cutover or rollback.",
    )
    parser.add_argument("--plan-token")
    parser.add_argument(
        "--execution-json-stdin",
        action="store_true",
        help=(
            "Read reviewed execution JSON from stdin. Execute requires "
            "plan_token and new_password; rollback accepts only plan_token."
        ),
    )
    parser.add_argument(
        "--credential-json-stdin",
        action="store_true",
        help="Verify the runtime binding and optional staff credential via stdin.",
    )
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.action == "plan":
        if args.plan_token or args.execution_json_stdin or args.credential_json_stdin:
            parser.error("plan does not accept execution input")
        return
    if args.action == "verify":
        if args.plan_token or args.execution_json_stdin or args.for_action != "cutover":
            parser.error("verify does not accept plan or execution input")
        return
    if args.credential_json_stdin:
        parser.error("credential verification input is accepted only by verify")
    if args.for_action != "cutover":
        parser.error("--for-action is accepted only by plan")
    if args.action == "execute" and not args.execution_json_stdin:
        parser.error("execute requires protected execution JSON on stdin")
    if args.execution_json_stdin:
        if args.plan_token:
            parser.error(
                "--execution-json-stdin cannot be combined with --plan-token"
            )
        return
    if not args.plan_token:
        parser.error("execute requires --plan-token from a fresh plan")


def _read_json_input(stream: Any | None = None) -> dict[str, Any]:
    source = stream if stream is not None else sys.stdin.buffer
    payload = source.read(MAX_EXECUTION_INPUT_BYTES + 1)
    if len(payload) > MAX_EXECUTION_INPUT_BYTES:
        raise ValueError("Execution input is too large")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Execution input must be valid UTF-8 JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Execution input must be a JSON object")
    return decoded


def read_execution_input(
    stream: Any | None = None,
    *,
    require_password: bool,
) -> tuple[str, str | None]:
    decoded = _read_json_input(stream)
    expected = {"plan_token", "new_password"} if require_password else {"plan_token"}
    if set(decoded) != expected:
        raise ValueError("Execution input has an unexpected schema")
    token = decoded["plan_token"]
    if not isinstance(token, str) or not token or len(token) > 512:
        raise ValueError("Execution input plan token is invalid")
    password = decoded.get("new_password")
    if require_password and (not isinstance(password, str) or not password):
        raise ValueError("Execution input credential is invalid")
    return token, password


def read_credential_input(
    stream: Any | None = None,
) -> tuple[str | None, str]:
    decoded = _read_json_input(stream)
    if set(decoded) not in (
        {"binding_challenge"},
        {"binding_challenge", "new_password"},
    ):
        raise ValueError("Credential input has an unexpected schema")
    password = decoded.get("new_password")
    if password is not None and (not isinstance(password, str) or not password):
        raise ValueError("Credential input is invalid")
    challenge = decoded["binding_challenge"]
    if (
        not isinstance(challenge, str)
        or len(challenge) != 64
        or any(character not in "0123456789abcdef" for character in challenge)
    ):
        raise ValueError("Credential binding challenge is invalid")
    return password, challenge


async def run(args: argparse.Namespace) -> dict[str, Any]:
    from core.database import async_session_maker

    execution_token = args.plan_token
    new_password: str | None = None
    if args.execution_json_stdin:
        execution_token, new_password = read_execution_input(
            require_password=args.action == "execute"
        )
    verification_credential: str | None = None
    binding_challenge: str | None = None
    if args.credential_json_stdin:
        verification_credential, binding_challenge = read_credential_input()
    async with async_session_maker() as session:
        try:
            if args.action == "plan":
                return await LegacyOwnerCutoverService.plan(
                    session,
                    for_action=args.for_action,
                )
            if args.action == "verify":
                if binding_challenge is None:
                    raise ValueError("Credential binding challenge is required")
                return await LegacyOwnerCutoverService.verify(
                    session,
                    staff_credential=verification_credential,
                    binding_challenge=binding_challenge,
                )
            operation = (
                LegacyOwnerCutoverService.rollback
                if args.action == "rollback"
                else LegacyOwnerCutoverService.execute
            )
            operation_kwargs = {"plan_token": str(execution_token or "")}
            if args.action == "execute":
                operation_kwargs["new_password"] = str(new_password or "")
            result = await operation(session, **operation_kwargs)
            await session.commit()
            return result
        except Exception:
            if args.action in {"execute", "rollback"}:
                await session.rollback()
            raise


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    try:
        result = asyncio.run(run(args))
    except (LegacyOwnerCutoverBlockedError, ValueError) as exc:
        print(f"legacy_owner_cutover status=blocked error={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except IntegrityError as exc:
        print(
            "legacy_owner_cutover status=blocked "
            "error=database state changed concurrently",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    except Exception as exc:
        print(
            "legacy_owner_cutover status=error "
            "error=unexpected transaction failure",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("ready") is False:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
