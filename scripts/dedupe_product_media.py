#!/usr/bin/env python3
"""Deduplicate product media URLs into shared hash-based WEBP storage.

Default mode is dry-run.
Use --execute to persist DB updates and delete unreferenced old files.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(".")

from core.config import settings
from models import ImportMediaCache, Product, ProductImage


@dataclass
class UrlPlan:
    old_url: str
    canonical_url: str
    old_path: Path
    canonical_path: Path
    webp_content: bytes
    old_size: int


def _url_to_path(url: str) -> Path:
    return Path(url.lstrip("/"))


def _to_webp(content: bytes) -> bytes:
    img = Image.open(BytesIO(content))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    output = BytesIO()
    img.save(output, format="WEBP", quality=85)
    return output.getvalue()


async def _build_plan(url: str) -> Optional[UrlPlan]:
    if not url or not str(url).startswith("/media/"):
        return None

    old_path = _url_to_path(url)
    if not old_path.exists() or not old_path.is_file():
        return None

    old_bytes = await asyncio.to_thread(old_path.read_bytes)
    webp_content = await asyncio.to_thread(_to_webp, old_bytes)
    content_hash = hashlib.sha256(webp_content).hexdigest()
    canonical_url = f"/media/products/shared/{content_hash}.webp"
    canonical_path = _url_to_path(canonical_url)

    if canonical_url == url:
        return None

    return UrlPlan(
        old_url=url,
        canonical_url=canonical_url,
        old_path=old_path,
        canonical_path=canonical_path,
        webp_content=webp_content,
        old_size=len(old_bytes),
    )


async def _collect_media_urls(session: AsyncSession) -> List[str]:
    urls: List[str] = []

    main_rows = await session.execute(select(Product.main_image).where(Product.main_image.is_not(None)))
    urls.extend([u for u in main_rows.scalars().all() if u and str(u).startswith("/media/")])

    gallery_rows = await session.execute(select(ProductImage.url))
    urls.extend([u for u in gallery_rows.scalars().all() if u and str(u).startswith("/media/")])

    unique: Dict[str, None] = {}
    for url in urls:
        unique[str(url)] = None
    return list(unique.keys())


async def _count_refs(session: AsyncSession, url: str) -> int:
    main_refs = (
        await session.execute(select(func.count()).select_from(Product).where(Product.main_image == url))
    ).scalar_one()
    gallery_refs = (
        await session.execute(select(func.count()).select_from(ProductImage).where(ProductImage.url == url))
    ).scalar_one()
    cache_refs = (
        await session.execute(select(func.count()).select_from(ImportMediaCache).where(ImportMediaCache.local_url == url))
    ).scalar_one()
    return int(main_refs or 0) + int(gallery_refs or 0) + int(cache_refs or 0)


async def run(*, execute: bool) -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            urls = await _collect_media_urls(session)
            plans: List[UrlPlan] = []
            skipped = 0
            for url in urls:
                try:
                    plan = await _build_plan(url)
                except Exception as exc:
                    skipped += 1
                    print(f"[warn] skip {url}: {exc}")
                    continue
                if plan is None:
                    continue
                plans.append(plan)

            if not plans:
                print("No replaceable media duplicates found.")
                return

            replace_map = {plan.old_url: plan.canonical_url for plan in plans}
            total_old_bytes = sum(plan.old_size for plan in plans)
            groups: Dict[str, List[UrlPlan]] = {}
            for plan in plans:
                groups.setdefault(plan.canonical_url, []).append(plan)
            duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}
            potential_reclaimed = sum(plan.old_size for plan in plans)
            print(f"Candidates: {len(plans)} unique media URLs")
            print(f"Approx source size: {total_old_bytes} bytes")
            print(f"Potential reclaim (after canonical rewrite): {potential_reclaimed} bytes")
            print(f"Hash groups: {len(groups)} (duplicate groups: {len(duplicate_groups)})")
            print(f"Skipped unreadable files: {skipped}")
            if duplicate_groups:
                print("Top duplicate hash groups:")
                ranked = sorted(
                    duplicate_groups.items(),
                    key=lambda item: (len(item[1]), sum(p.old_size for p in item[1])),
                    reverse=True,
                )
                for canonical_url, group_plans in ranked[:10]:
                    group_size = sum(item.old_size for item in group_plans)
                    print(f"  {canonical_url}: {len(group_plans)} files, {group_size} bytes")

            print("URLs to rewrite:")
            for sample in plans:
                print(f"  {sample.old_url} -> {sample.canonical_url}")

            if not execute:
                print("\nDry run only. Re-run with --execute to apply.")
                return

            # 1) Ensure canonical files exist.
            for plan in plans:
                plan.canonical_path.parent.mkdir(parents=True, exist_ok=True)
                if not plan.canonical_path.exists():
                    await asyncio.to_thread(plan.canonical_path.write_bytes, plan.webp_content)

            # 2) Rewrite DB URLs to canonical shared paths.
            for old_url, canonical_url in replace_map.items():
                await session.execute(
                    update(Product).where(Product.main_image == old_url).values(main_image=canonical_url)
                )
                await session.execute(
                    update(ProductImage).where(ProductImage.url == old_url).values(url=canonical_url)
                )
                await session.execute(
                    update(ImportMediaCache).where(ImportMediaCache.local_url == old_url).values(local_url=canonical_url)
                )
            await session.commit()

            # 3) Remove old files if truly unreferenced.
            deleted = 0
            reclaimed = 0
            for plan in plans:
                refs = await _count_refs(session, plan.old_url)
                if refs > 0:
                    continue
                if not plan.old_path.exists():
                    continue
                try:
                    size = plan.old_path.stat().st_size
                    await asyncio.to_thread(os.remove, plan.old_path)
                    deleted += 1
                    reclaimed += int(size)
                except Exception as exc:
                    print(f"[warn] failed to delete {plan.old_path}: {exc}")

            print("\nApplied successfully.")
            print(f"Updated URLs: {len(plans)}")
            print(f"Deleted orphan files: {deleted}")
            print(f"Reclaimed bytes: {reclaimed}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deduplicate product media to canonical shared WEBP files."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply DB updates and remove orphan files. Default: dry-run.",
    )
    args = parser.parse_args()
    asyncio.run(run(execute=args.execute))


if __name__ == "__main__":
    main()
