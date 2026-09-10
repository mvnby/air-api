#!/usr/bin/env python3
"""Fail a release when this node cannot read existing integration credentials."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from core.database import async_session_maker, engine
from services.integration_credential_health import integration_credential_health


async def main() -> int:
    try:
        async with async_session_maker() as session:
            if session.get_bind().dialect.name == "postgresql":
                await session.execute(text("SET TRANSACTION READ ONLY"))
            result = await integration_credential_health(session)
        print(json.dumps(result))
        return 0 if result["status"] == "passed" else 1
    except Exception:
        # Exception messages may contain connection strings or encrypted values.
        print(json.dumps({"status": "failed", "error_code": "credential_health_unavailable"}))
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
