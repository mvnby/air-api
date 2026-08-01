"""Service-layer helpers for manager specs operations."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Product
from schemas import BulkSpecUpdate
from services.brand_series_service import SERIES_SPEC_KEYS, sync_product_brand_series
from services.catalog_revision_service import CatalogRevisionService
from services.spec_normalizer import normalize_specs


SERIES_SPEC_KEY_LOOKUP = {key.strip().lower() for key in SERIES_SPEC_KEYS}


def _payload_touches_series(payload: BulkSpecUpdate) -> bool:
    if payload.operation == "replace":
        return True
    if payload.operation != "delete_keys":
        return False
    return any(str(key).strip().lower() in SERIES_SPEC_KEY_LOOKUP for key in payload.specs.keys())


def _delete_spec_key(current_specs: dict, key: str) -> None:
    normalized_key = str(key).strip().lower()
    if normalized_key in SERIES_SPEC_KEY_LOOKUP:
        for existing_key in list(current_specs.keys()):
            if str(existing_key).strip().lower() in SERIES_SPEC_KEY_LOOKUP:
                current_specs.pop(existing_key, None)
        return

    current_specs.pop(key, None)


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
        updated_product_ids: list[int] = []
        clear_series_when_missing = _payload_touches_series(payload)
        for product in products:
            current_specs = dict(product.specs) if product.specs else {}

            if payload.operation == "replace":
                current_specs = dict(payload.specs)
            elif payload.operation == "delete_keys":
                for key in payload.specs.keys():
                    _delete_spec_key(current_specs, str(key))
            else:
                current_specs.update(payload.specs)

            product.specs = normalize_specs(current_specs)
            await sync_product_brand_series(
                session,
                product=product,
                specs=product.specs,
                title=product.title or "",
                allow_series_tag_fallback=False,
                allow_series_title_fallback=False,
                clear_series_when_missing=clear_series_when_missing,
            )
            session.add(product)
            updated_count += 1
            if product.id is not None:
                updated_product_ids.append(int(product.id))

        if updated_product_ids:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="manager_specs_bulk_update",
                product_ids=updated_product_ids,
            )
            await session.commit()
        else:
            await session.commit()
        return {
            "message": f"Updated specs for {updated_count} products",
            "operation": payload.operation,
        }
