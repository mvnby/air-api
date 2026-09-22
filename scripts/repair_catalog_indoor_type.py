"""Plan or execute an exact, narrow indoor-unit filter repair.

Run inside the deployed API image. Planning is read-only; execution requires
the exact plan digest and refuses a PostgreSQL replica.
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
from services.catalog_indoor_type_repair import indoor_repair_plan  # noqa: E402
from services.catalog_revision_service import CatalogRevisionService  # noqa: E402


async def run(*, execute_plan_digest: str | None) -> dict:
    async with async_session_maker() as session:
        if execute_plan_digest is None:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        else:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        is_replica = bool(await session.scalar(text("SELECT pg_is_in_recovery()")))
        if execute_plan_digest is not None and is_replica:
            raise RuntimeError("Indoor-type repair must execute on the PostgreSQL primary")

        query = select(Product).order_by(Product.id)
        if execute_plan_digest is not None:
            query = query.with_for_update(of=Product)
        products = (await session.execute(query)).scalars().all()
        plan, changes = indoor_repair_plan(products)
        if execute_plan_digest is None:
            await session.rollback()
            return {"mode": "plan", "replica": is_replica, **plan}
        if execute_plan_digest != plan["plan_digest"]:
            raise RuntimeError("Catalog changed since the reviewed plan; run plan again")

        for product, updated in changes:
            product.specs = updated
            flag_modified(product, "specs")
            session.add(product)
        if changes:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="catalog_indoor_type_repair",
                product_ids=[product.id for product, _ in changes],
            )
        await session.commit()
        return {"mode": "execute", "replica": is_replica, **plan}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-plan-digest", metavar="SHA256", help="Apply only the exact reviewed plan")
    args = parser.parse_args()
    result = asyncio.run(run(execute_plan_digest=args.execute_plan_digest))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
