"""Read-only rollout report. This command deliberately cannot mutate data."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import async_session_maker
from models.tenancy import TenantScope
from services.leads_inbox_expiry_service import LeadsInboxExpiryService


async def report(args):
    scope = TenantScope(tenant_id=args.tenant_id, storefront_id=args.storefront_id, is_system=False)
    async with async_session_maker() as session:
        result = await LeadsInboxExpiryService.run(session, tenant_scope=scope, after_id=args.after_id, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--storefront-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--after-id", type=int, default=0)
    asyncio.run(report(parser.parse_args()))
