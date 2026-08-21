from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from crud.product_collection import ProductCollectionDAO
from models import ProductCollection
from models.tenancy import TenantScope
from services.manager_product_collection_service import ManagerProductCollectionService
from services.manager_product_collection_validation import ManagerProductCollectionValidation
from services.product_collection_catalog_access import ProductCollectionCatalogAccess


class CatalogDecisionCollectionService:
    """Atomic bridge from the short-lived manager basket to a draft collection."""

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        title: str,
        product_ids: list[int],
        tenant_scope: TenantScope,
        actor_username: str,
        actor_staff_user_id: int | None,
    ) -> dict:
        normalized_title = " ".join(title.split())
        if not normalized_title:
            raise HTTPException(status_code=400, detail="Укажите название подборки.")
        ids = [int(product_id) for product_id in product_ids]
        if len(ids) != len(set(ids)):
            raise HTTPException(status_code=400, detail="Один товар нельзя добавить дважды.")
        projections = await ProductCollectionCatalogAccess.visible_by_ids(
            session,
            tenant_scope=tenant_scope,
            product_ids=ids,
        )
        if len(projections) != len(ids):
            missing = [product_id for product_id in ids if product_id not in projections]
            raise HTTPException(
                status_code=404,
                detail=f"Товары недоступны для этой витрины: {', '.join(map(str, missing))}.",
            )

        slug = await ManagerProductCollectionValidation.unique_slug(
            session,
            requested=None,
            fallback=normalized_title,
            tenant_scope=tenant_scope,
        )
        collection = ProductCollection(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            slug=slug,
            internal_name=normalized_title,
            public_title=normalized_title,
            status="draft",
            mode="manual",
            sort_mode="recommended",
            min_items=1,
            max_items=max(6, len(ids)),
            rule_config={},
        )
        session.add(collection)
        await session.flush()

        async def stage_items() -> None:
            await ProductCollectionDAO.replace_items(
                session,
                collection_id=int(collection.id),
                tenant_scope=tenant_scope,
                items=[
                    {"product_id": product_id, "is_pinned": True, "editorial_note": None}
                    for product_id in ids
                ],
            )

        await ManagerProductCollectionService._commit_mutation(
            session,
            collection=collection,
            tenant_scope=tenant_scope,
            actor_username=actor_username,
            actor_staff_user_id=actor_staff_user_id,
            action="product_collection.created_from_catalog_decision",
            change_set={"product_ids": {"before": [], "after": ids}},
            stage_changes=stage_items,
        )
        return await ManagerProductCollectionService.get_collection(
            session,
            int(collection.id),
            tenant_scope=tenant_scope,
        )
