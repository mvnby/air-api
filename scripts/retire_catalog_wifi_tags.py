"""Plan or retire the two legacy product Wi-Fi tags after spec repair.

Run the user-confirmed MDV Wi-Fi repair first. This command refuses unresolved
conflicts, executes only on a primary with an exact digest, and leaves Feature
records (which may have similar slugs) unchanged.
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
from models import Product, ProductTagLink, Tag  # noqa: E402
from services.catalog_revision_service import CatalogRevisionService  # noqa: E402
from services.catalog_user_wifi_repair import load_user_wifi_manifest  # noqa: E402
from services.catalog_wifi_tag_retirement import wifi_tag_retirement_plan  # noqa: E402


async def run(*, execute_plan_digest: str | None) -> dict:
    confirmed = {
        entry["id"]: entry["new_state"]
        for entry in load_user_wifi_manifest()["wifi"]
    }
    async with async_session_maker() as session:
        if execute_plan_digest is None:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        else:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        is_replica = bool(await session.scalar(text("SELECT pg_is_in_recovery()")))
        if execute_plan_digest is not None and is_replica:
            raise RuntimeError("Wi-Fi tag retirement must run on the PostgreSQL primary")
        tag_query = select(Tag).where(Tag.slug.in_(("wifi-builtin", "wifi-ready"))).order_by(Tag.id)
        if execute_plan_digest is not None:
            tag_query = tag_query.with_for_update(of=Tag)
        tags = (await session.execute(tag_query)).scalars().all()
        tag_ids = [tag.id for tag in tags]
        link_query = select(ProductTagLink).where(ProductTagLink.tag_id.in_(tag_ids)).order_by(
            ProductTagLink.product_id, ProductTagLink.tag_id
        )
        if execute_plan_digest is not None:
            link_query = link_query.with_for_update(of=ProductTagLink)
        links = (await session.execute(link_query)).scalars().all()
        product_ids = sorted({link.product_id for link in links})
        product_query = select(Product).where(Product.id.in_(product_ids)).order_by(Product.id)
        if execute_plan_digest is not None:
            product_query = product_query.with_for_update(of=Product)
        products = (await session.execute(product_query)).scalars().all()
        plan, spec_changes = wifi_tag_retirement_plan(tags, links, products, confirmed)
        if execute_plan_digest is None:
            await session.rollback()
            return {"mode": "plan", "replica": is_replica, **plan}
        if execute_plan_digest != plan["plan_digest"]:
            raise RuntimeError("Wi-Fi tag state changed since the reviewed plan; run plan again")

        for product, specs in spec_changes:
            product.specs = specs
            flag_modified(product, "specs")
            session.add(product)
        for link in links:
            await session.delete(link)
        await session.flush()
        for tag in tags:
            await session.delete(tag)
        if links or tags:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="retire_legacy_wifi_tags",
                product_ids=product_ids,
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
