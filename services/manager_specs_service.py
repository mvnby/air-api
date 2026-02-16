"""Service-layer helpers for manager specs operations."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Product
from schemas import BulkSpecUpdate
from services.spec_normalizer import normalize_specs


class ManagerSpecsService:
    @staticmethod
    async def bulk_update_specs(
        session: AsyncSession,
        payload: BulkSpecUpdate,
    ) -> dict:
        stmt = select(Product).where(Product.id.in_(payload.product_ids))
        result = await session.execute(stmt)
        products = result.scalars().all()

        updated_count = 0
        for product in products:
            current_specs = dict(product.specs) if product.specs else {}

            if payload.operation == "replace":
                current_specs = dict(payload.specs)
            elif payload.operation == "delete_keys":
                for key in payload.specs.keys():
                    current_specs.pop(key, None)
            else:
                current_specs.update(payload.specs)

            product.specs = normalize_specs(current_specs)
            session.add(product)
            updated_count += 1

        await session.commit()
        return {
            "message": f"Updated specs for {updated_count} products",
            "operation": payload.operation,
        }
