import asyncio
import sys
from sqlmodel import select
from core.database import async_session_maker
from models import Product
from services.image_service import ImageService

async def migrate_images():
    print("Starting image migration...")
    
    async with async_session_maker() as session:
        # Fetch all products
        stmt = select(Product)
        result = await session.execute(stmt)
        products = result.scalars().all()
        
        print(f"Found {len(products)} products to check.")
        
        updated_count = 0
        
        for product in products:
            needs_save = False
            print(f"Checking product: {product.title} (Slug: {product.slug})")
            
            # 1. Main Image
            if product.main_image and product.main_image.startswith("http"):
                print(f"  Downloading main image: {product.main_image}")
                local_path = await ImageService.download_and_save_image(
                    product.main_image, 'products', product.slug
                )
                if local_path:
                    product.main_image = local_path
                    needs_save = True
                    print(f"  -> Saved to {local_path}")
                else:
                    print("  -> Failed to download")

            # 2. Gallery Images
            if product.images:
                new_images = []
                images_changed = False
                
                for img in product.images:
                    if img.startswith("http"):
                        print(f"  Downloading gallery image: {img}")
                        local_path = await ImageService.download_and_save_image(
                            img, 'products', product.slug
                        )
                        if local_path:
                            new_images.append(local_path)
                            images_changed = True
                            print(f"  -> Saved to {local_path}")
                        else:
                            # Keep original URL if failed? Or skip?
                            # Better keep original to retry later, but user wants local.
                            # Let's keep original if failed so we don't lose data.
                            new_images.append(img)
                            print("  -> Failed to download, keeping original")
                    else:
                        new_images.append(img)
                
                if images_changed:
                    product.images = new_images
                    needs_save = True

            if needs_save:
                session.add(product)
                updated_count += 1
                
        if updated_count > 0:
            await session.commit()
            print(f"Committed changes for {updated_count} products.")
        else:
            print("No updates needed.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(migrate_images())
