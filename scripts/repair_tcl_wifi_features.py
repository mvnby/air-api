"""Plan or move mixed TCL series Wi-Fi features onto built-in-module models."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import text
from sqlmodel import select

sys.path.append(".")

from core.database import async_session_maker  # noqa: E402
from models import Feature, FeatureProductLink, FeatureSeriesLink, Product  # noqa: E402
from services.catalog_revision_service import CatalogRevisionService  # noqa: E402
from services.catalog_tcl_wifi_feature_repair import (  # noqa: E402
    EXPECTED_PRODUCTS,
    EXPECTED_SERIES_LINKS,
    tcl_wifi_feature_plan,
)


async def run(*, execute_plan_digest: str | None) -> dict:
    async with async_session_maker() as session:
        if execute_plan_digest is None:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        else:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        is_replica = bool(await session.scalar(text("SELECT pg_is_in_recovery()")))
        if execute_plan_digest is not None and is_replica:
            raise RuntimeError("TCL feature repair must execute on the PostgreSQL primary")
        feature_rows = (await session.execute(select(Feature.id, Feature.slug).where(Feature.id.in_((27, 40))))).all()
        if {feature_id: slug for feature_id, slug in feature_rows} != {27: "vstroennyi-wi-fi-modul", 40: "vstroennyi-wi-fi"}:
            raise RuntimeError("Reviewed Wi-Fi features changed")
        products_query = select(Product).where(Product.id.in_(EXPECTED_PRODUCTS)).order_by(Product.id)
        series_query = select(FeatureSeriesLink).where(
            FeatureSeriesLink.series_id.in_((10, 189)),
            FeatureSeriesLink.feature_id.in_((27, 40)),
        )
        links_query = select(FeatureProductLink).where(
            FeatureProductLink.product_id.in_(EXPECTED_PRODUCTS),
            FeatureProductLink.feature_id.in_((27, 40)),
        )
        if execute_plan_digest is not None:
            products_query = products_query.with_for_update(of=Product)
            series_query = series_query.with_for_update(of=FeatureSeriesLink)
            links_query = links_query.with_for_update(of=FeatureProductLink)
        products = (await session.execute(products_query)).scalars().all()
        series_links = (await session.execute(series_query)).scalars().all()
        product_links = (await session.execute(links_query)).scalars().all()
        plan, disables, additions = tcl_wifi_feature_plan(products, series_links, product_links)
        if execute_plan_digest is None:
            await session.rollback()
            return {"mode": "plan", "replica": is_replica, **plan}
        if execute_plan_digest != plan["plan_digest"]:
            raise RuntimeError("Catalog changed since the reviewed plan; run plan again")
        for link in disables:
            link.is_enabled = False
            session.add(link)
        for product_id, feature_id, sort_order in additions:
            session.add(FeatureProductLink(
                product_id=product_id,
                feature_id=feature_id,
                source="manual",
                is_enabled=True,
                sort_order=sort_order,
            ))
        if plan["changed"]:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="tcl_wifi_feature_repair",
                product_ids=sorted(EXPECTED_PRODUCTS),
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
