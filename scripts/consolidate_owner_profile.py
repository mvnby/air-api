"""Fixed owner-profile plan/execute; protected inputs travel only on stdin."""

import argparse
import asyncio
import json
import sys

sys.path.append(".")

from scripts.cutover_legacy_owner import _read_json_input
from services.owner_profile_consolidation_service import OwnerProfileConsolidationService


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "execute", "verify"))
    parser.add_argument("--protected-json-stdin", action="store_true")
    return parser


async def run(args):
    from core.database import async_session_maker
    payload = _read_json_input() if args.protected_json_stdin else {}
    expected = {"plan_token"} if args.action == "execute" else {"binding_challenge"} if args.action == "verify" else set()
    if set(payload) != expected:
        raise ValueError("Unexpected protected input schema")
    async with async_session_maker() as session:
        try:
            result = await getattr(OwnerProfileConsolidationService, args.action)(session, **payload)
            if args.action == "execute":
                await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.protected_json_stdin != (args.action != "plan"):
        parser.error("execute/verify require protected stdin; plan accepts no input")
    try:
        result = asyncio.run(run(args))
    except Exception:
        # Database errors can contain bound profile data: never print them.
        print("owner_profile_consolidation status=blocked", file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    if not result["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
