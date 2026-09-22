"""Plan or add six missing TCL Wi-Fi tags from verified existing specs."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict

from sqlalchemy import text
from sqlmodel import select

sys.path.append(".")

from core.database import async_session_maker  # noqa: E402
from models import Product, ProductTagLink, Tag  # noqa: E402
from services.catalog_revision_service import CatalogRevisionService  # noqa: E402
from services.catalog_wifi_tag_repair import WIFI_TAG_CORRECTIONS, WIFI_TAG_SLUGS, wifi_tag_repair_plan  # noqa: E402


async def run(*, execute_plan_digest: str | None) -> dict:
    async with async_session_maker() as session:
        if execute_plan_digest is None:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        else:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        is_replica = bool(await session.scalar(text("SELECT pg_is_in_recovery()")))
        if execute_plan_digest is not None and is_replica:
            raise RuntimeError("Wi-Fi tag repair must execute on the PostgreSQL primary")

        tags = (await session.execute(select(Tag).where(Tag.slug.in_(WIFI_TAG_SLUGS)))).scalars().all()
        tag_ids = {tag.slug: tag.id for tag in tags}
        if set(tag_ids) != WIFI_TAG_SLUGS:
            raise RuntimeError("Both canonical Wi-Fi tags must already exist")
        query = select(Product).where(Product.id.in_(WIFI_TAG_CORRECTIONS)).order_by(Product.id)
        if execute_plan_digest is not None:
            query = query.with_for_update(of=Product)
        products = (await session.execute(query)).scalars().all()
        tag_rows = (await session.execute(
            select(ProductTagLink.product_id, Tag.slug)
            .join(Tag, Tag.id == ProductTagLink.tag_id)
            .where(ProductTagLink.product_id.in_(WIFI_TAG_CORRECTIONS))
        )).all()
        tags_by_product: dict[int, list[str]] = defaultdict(list)
        for product_id, slug in tag_rows:
            tags_by_product[product_id].append(slug)
        plan, additions = wifi_tag_repair_plan(products, tags_by_product)
        if execute_plan_digest is None:
            await session.rollback()
            return {"mode": "plan", "replica": is_replica, **plan}
        if execute_plan_digest != plan["plan_digest"]:
            raise RuntimeError("Catalog changed since the reviewed plan; run plan again")
        for product, tag_slug in additions:
            session.add(ProductTagLink(product_id=product.id, tag_id=tag_ids[tag_slug]))
        if additions:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="catalog_wifi_tag_repair",
                product_ids=[product.id for product, _ in additions],
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
