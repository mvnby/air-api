#!/usr/bin/env python3
"""
Data Migration Script: Clean and Slugify Products
- Deletes products without source_link
- Generates slugs from source_link (brand + model)
"""
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from core.database import get_session
from models import Product


def extract_slug_from_url(url: str) -> str:
    """
    Extract slug from Onliner URL.
    Example: https://catalog.onliner.by/conditioners/chigo/cs71v3g1d211ae5b
    Returns: chigo-cs71v3g1d211ae5b
    """
    if not url:
        return ""
    
    parsed = urlparse(url)
    path = parsed.path.strip('/')
    segments = [s for s in path.split('/') if s]
    
    # Take last 2 segments (brand + model)
    if len(segments) >= 2:
        brand = segments[-2]
        model = segments[-1]
        slug = f"{brand}-{model}".lower()
    elif len(segments) == 1:
        # Fallback: use last segment only
        slug = segments[-1].lower()
    else:
        return ""
    
    return slug


async def clean_and_slugify():
    """Main migration function"""
    async for session in get_session():
        try:
            # 1. Fetch all products
            stmt = select(Product)
            result = await session.execute(stmt)
            products = result.scalars().all()
            
            deleted_count = 0
            updated_count = 0
            skipped_count = 0
            
            print(f"Found {len(products)} products")
            print("-" * 60)
            
            for product in products:
                # Delete if no source_link
                if not product.source_url or product.source_url.strip() == "":
                    print(f"❌ Deleting: {product.title} (no source_link)")
                    await session.delete(product)
                    deleted_count += 1
                    continue
                
                # Generate slug
                slug = extract_slug_from_url(product.source_url)
                
                if not slug:
                    print(f"⚠️  Skipping: {product.title} (couldn't extract slug)")
                    skipped_count += 1
                    continue
                
                # Check for duplicates
                existing_stmt = select(Product).where(Product.slug == slug, Product.id != product.id)
                existing_result = await session.execute(existing_stmt)
                existing = existing_result.scalar_one_or_none()
                
                if existing:
                    # Add product ID to make unique
                    slug = f"{slug}-{product.id}"
                    print(f"⚠️  Duplicate slug detected, using: {slug}")
                
                product.slug = slug
                session.add(product)
                updated_count += 1
                print(f"✅ Updated: {product.title} → {slug}")
            
            # Commit changes
            await session.commit()
            
            print("-" * 60)
            print(f"✅ Migration complete!")
            print(f"   Updated: {updated_count}")
            print(f"   Deleted: {deleted_count}")
            print(f"   Skipped: {skipped_count}")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error: {e}")
            raise
        finally:
            await session.close()
        break  # Exit after first session


if __name__ == "__main__":
    print("Starting Product Slug Migration...")
    print("=" * 60)
    asyncio.run(clean_and_slugify())
