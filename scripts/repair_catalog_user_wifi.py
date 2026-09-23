"""Plan or apply the catalog owner's exact MDV Wi-Fi confirmations.

Planning is read-only. Execution needs the fresh plan digest, the PostgreSQL
primary, and the production deploy lock.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import text
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

sys.path.append(".")

from core.database import async_session_maker  # noqa: E402
from models import Product  # noqa: E402
from services.catalog_revision_service import CatalogRevisionService  # noqa: E402
from services.catalog_user_wifi_repair import load_user_wifi_manifest, user_wifi_repair_plan  # noqa: E402


async def run(*, execute_plan_digest: str | None) -> dict:
    manifest = load_user_wifi_manifest()
    ids = sorted(entry["id"] for entry in manifest["wifi"])
    async with async_session_maker() as session:
        if execute_plan_digest is None:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        else:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        is_replica = bool(await session.scalar(text("SELECT pg_is_in_recovery()")))
        if execute_plan_digest is not None and is_replica:
            raise RuntimeError("User-confirmed Wi-Fi repair must run on the PostgreSQL primary")
        query = select(Product).where(Product.id.in_(ids)).order_by(Product.id)
        if execute_plan_digest is not None:
            query = query.with_for_update(of=Product)
        products = (await session.execute(query)).scalars().all()
        plan, changes = user_wifi_repair_plan(products, manifest)
        if execute_plan_digest is None:
            await session.rollback()
            return {"mode": "plan", "replica": is_replica, **plan}
        if execute_plan_digest != plan["plan_digest"]:
            raise RuntimeError("Catalog changed since the reviewed Wi-Fi plan; run plan again")

        for product, specs in changes:
            product.specs = specs
            flag_modified(product, "specs")
            session.add(product)
        if changes:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="mdv_user_confirmed_wifi_repair",
                product_ids=[product.id for product, _ in changes],
            )
        await session.commit()
        return {"mode": "execute", "replica": is_replica, **plan}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-plan-digest", metavar="SHA256", help="Apply only the exact reviewed plan")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(execute_plan_digest=args.execute_plan_digest)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
