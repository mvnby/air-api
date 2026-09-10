#!/usr/bin/env python3
"""Plan or execute one reviewed integration-credential rewrap transaction."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import async_session_maker, engine  # noqa: E402
from sqlalchemy import text  # noqa: E402
from services.integration_credential_rotation_service import (  # noqa: E402
    IntegrationCredentialRotationService,
)
from services.integration_credential_rotation_token import (  # noqa: E402
    IntegrationCredentialRotationBlockedError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read or atomically rewrap persisted integration credentials. "
            "Execute accepts only the unexpired token from an exact plan."
        )
    )
    parser.add_argument("action", choices=("plan", "execute"))
    parser.add_argument("--plan-token")
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.action == "plan" and args.plan_token:
        parser.error("plan does not accept --plan-token")
    if args.action == "execute" and not args.plan_token:
        parser.error("execute requires --plan-token from a fresh plan")


async def run(args: argparse.Namespace) -> dict[str, Any]:
    async with async_session_maker() as session:
        try:
            if args.action == "plan":
                if session.get_bind().dialect.name == "postgresql":
                    await session.execute(text("SET TRANSACTION READ ONLY"))
                result = await IntegrationCredentialRotationService.plan(session)
                token = result.get("plan_token")
                result["reviewed_execute_command"] = (
                    shlex.join(
                        [
                            "python3",
                            "scripts/manage_integration_credential_rewrap.py",
                            "execute",
                            "--plan-token",
                            str(token),
                        ]
                    )
                    if token
                    else None
                )
                return result
            result = await IntegrationCredentialRotationService.execute(
                session,
                plan_token=str(args.plan_token),
            )
            await session.commit()
            return result
        except Exception:
            if args.action == "execute":
                await session.rollback()
            raise


async def async_main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    try:
        result = await run(args)
    except IntegrationCredentialRotationBlockedError as exc:
        print(
            json.dumps({"status": "blocked", "error": str(exc)}),
            file=sys.stderr,
        )
        return 2
    except Exception:
        print(
            json.dumps(
                {"status": "error", "error_code": "credential_rewrap_failed"}
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        await engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ready", True) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
