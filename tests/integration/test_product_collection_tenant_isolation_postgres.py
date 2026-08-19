from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from crud.product_collection import ProductCollectionDAO
from models import (
    Feature,
    FeatureCategory,
    FeatureProductLink,
    Product,
    ProductCollection,
    ProductCollectionItem,
    ProductCollectionPlacement,
    Storefront,
    Tenant,
    TenantCatalogGrant,
    TenantOffer,
)
from models.tenancy import TenantScope
from services.manager_product_collection_service import ManagerProductCollectionService
from services.product_collection_catalog_access import ProductCollectionCatalogAccess
from services.product_collection_resolver import ProductCollectionResolver


async def _seed_two_scopes(db):
    tenants = [
        Tenant(
            slug=f"collection-scope-{suffix}",
            display_name=f"Collection scope {suffix}",
            status="active",
            is_system=False,
        )
        for suffix in ("a", "b")
    ]
    db.add_all(tenants)
    await db.flush()
    storefronts = [
        Storefront(
            tenant_id=int(tenant.id),
            slug="main",
            display_name=tenant.display_name,
            status="active",
            is_default=True,
        )
        for tenant in tenants
    ]
    products = [
        Product(
            title=f"Scoped product {suffix}",
            slug=f"scoped-product-{suffix}",
            price=10_000,
            is_published=True,
        )
        for suffix in ("a", "b")
    ]
    db.add_all([*storefronts, *products])
    await db.flush()
    feature_category = FeatureCategory(
        slug="collection-scope-features",
        name="Collection scope features",
    )
    db.add(feature_category)
    await db.flush()
    features = [
        Feature(
            slug=f"collection-scope-feature-{suffix}",
            name=f"Collection scope feature {suffix}",
            category_id=int(feature_category.id),
            scope_type="product",
        )
        for suffix in ("a", "b")
    ]
    db.add_all(features)
    await db.flush()
    db.add_all(
        FeatureProductLink(
            product_id=int(product.id),
            feature_id=int(feature.id),
        )
        for product, feature in zip(products, features, strict=True)
    )
    grants = [
        TenantCatalogGrant(
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
            status="active",
            revision=1,
            created_by_username="test",
            updated_by_username="test",
        )
        for tenant, storefront in zip(tenants, storefronts, strict=True)
    ]
    db.add_all(grants)
    await db.flush()
    offers = [
        TenantOffer(
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
            product_id=int(product.id),
            catalog_grant_id=int(grant.id),
            price=7_000 + index,
            is_published=True,
            status="active",
            price_source="inherited_master",
            created_by_username="test",
            updated_by_username="test",
        )
        for index, (tenant, storefront, product, grant) in enumerate(
            zip(tenants, storefronts, products, grants, strict=True)
        )
    ]
    collections = [
        ProductCollection(
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
            slug="featured",
            internal_name=f"Featured {index}",
            public_title=f"Featured {index}",
            status="published",
            mode="manual",
            min_items=1,
            max_items=6,
        )
        for index, (tenant, storefront) in enumerate(
            zip(tenants, storefronts, strict=True)
        )
    ]
    db.add_all([*offers, *collections])
    await db.flush()
    for tenant, storefront, product, collection in zip(
        tenants,
        storefronts,
        products,
        collections,
        strict=True,
    ):
        db.add_all(
            [
                ProductCollectionItem(
                    tenant_id=int(tenant.id),
                    storefront_id=int(storefront.id),
                    collection_id=int(collection.id),
                    product_id=int(product.id),
                    position=0,
                ),
                ProductCollectionPlacement(
                    tenant_id=int(tenant.id),
                    storefront_id=int(storefront.id),
                    collection_id=int(collection.id),
                    surface_key="yandex_business",
                    slot_key="categories",
                    position=0,
                ),
            ]
        )
    await db.commit()
    scopes = [
        TenantScope(
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
            is_system=False,
        )
        for tenant, storefront in zip(tenants, storefronts, strict=True)
    ]
    return scopes, products, collections


@pytest.mark.asyncio
async def test_collections_and_effective_prices_are_exact_storefront_scoped(db):
    scopes, products, collections = await _seed_two_scopes(db)

    for index, scope in enumerate(scopes):
        rows = await ProductCollectionDAO.list_all(db, tenant_scope=scope)
        assert [int(row.id) for row in rows] == [int(collections[index].id)]
        resolved = await ProductCollectionResolver.resolve_placement(
            db,
            surface_key="yandex_business",
            slot_key="categories",
            tenant_scope=scope,
        )
        assert [row["slug"] for row in resolved["collections"]] == ["featured"]
        item = resolved["collections"][0]["items"][0]
        assert item["product"].id == products[index].id
        assert item["product"].price == 7_000 + index
        rule_options = await ManagerProductCollectionService.get_rule_options(
            db,
            tenant_scope=scope,
        )
        assert [option["label"] for option in rule_options["features"]] == [
            f"Collection scope feature {'ab'[index]}"
        ]

    with pytest.raises(HTTPException) as foreign_read:
        await ManagerProductCollectionService.get_collection(
            db,
            int(collections[1].id),
            tenant_scope=scopes[0],
        )
    assert foreign_read.value.status_code == 404

    with pytest.raises(HTTPException) as foreign_product:
        await ManagerProductCollectionService.replace_items(
            db,
            int(collections[0].id),
            [{"product_id": int(products[1].id), "is_pinned": True}],
            tenant_scope=scopes[0],
            actor_username="tenant-a",
            actor_staff_user_id=None,
        )
    assert foreign_product.value.status_code == 404


@pytest.mark.asyncio
async def test_composite_foreign_keys_reject_cross_storefront_fallback_and_child(
    db_engine,
):
    factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        scopes, products, collections = await _seed_two_scopes(session)
        foreign_collection_id = int(collections[1].id)
        local_product_id = int(products[0].id)

        await session.execute(
            update(ProductCollection)
            .where(ProductCollection.id == int(collections[0].id))
            .values(fallback_collection_id=foreign_collection_id)
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        session.add(
            ProductCollectionItem(
                tenant_id=scopes[0].tenant_id,
                storefront_id=scopes[0].storefront_id,
                collection_id=foreign_collection_id,
                product_id=local_product_id,
                position=10,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_deleting_same_scope_fallback_only_nulls_fallback_reference(db):
    scopes, _, collections = await _seed_two_scopes(db)
    scope = scopes[0]
    primary = collections[0]
    fallback = ProductCollection(
        tenant_id=scope.tenant_id,
        storefront_id=scope.storefront_id,
        slug="same-scope-fallback",
        internal_name="Same scope fallback",
        public_title="Same scope fallback",
        status="draft",
        mode="manual",
        min_items=1,
        max_items=6,
    )
    db.add(fallback)
    await db.flush()
    primary.fallback_collection_id = int(fallback.id)
    await db.commit()

    await db.delete(fallback)
    await db.commit()
    await db.refresh(primary)

    assert primary.fallback_collection_id is None
    assert primary.tenant_id == scope.tenant_id
    assert primary.storefront_id == scope.storefront_id


@pytest.mark.asyncio
async def test_non_system_collections_require_an_exact_active_catalog_grant(db):
    scopes, products, collections = await _seed_two_scopes(db)
    scope = scopes[0]
    ungranted = Product(
        title="Ungrantable scoped product",
        slug="ungrantable-scoped-product",
        price=11_000,
        is_published=True,
    )
    direct_offer_product = Product(
        title="Direct offer product",
        slug="direct-offer-product",
        price=12_000,
        is_published=True,
    )
    inactive_grant = (
        await db.execute(
            select(TenantCatalogGrant).where(
                TenantCatalogGrant.tenant_id == scope.tenant_id,
                TenantCatalogGrant.storefront_id == scope.storefront_id,
            )
        )
    ).scalar_one()
    inactive_grant.status = "disabled"
    db.add_all([ungranted, direct_offer_product, inactive_grant])
    await db.flush()
    db.add(
        TenantOffer(
            tenant_id=scope.tenant_id,
            storefront_id=scope.storefront_id,
            product_id=int(ungranted.id),
            catalog_grant_id=int(inactive_grant.id),
            price=8_500,
            is_published=True,
            status="active",
            price_source="inherited_master",
            created_by_username="test",
            updated_by_username="test",
        )
    )
    db.add(
        TenantOffer(
            tenant_id=scope.tenant_id,
            storefront_id=scope.storefront_id,
            product_id=int(direct_offer_product.id),
            catalog_grant_id=None,
            price=8_600,
            is_published=True,
            status="active",
            price_source="manual",
            created_by_username="test",
            updated_by_username="test",
        )
    )
    db.add(
        ProductCollectionItem(
            tenant_id=scope.tenant_id,
            storefront_id=scope.storefront_id,
            collection_id=int(collections[0].id),
            product_id=int(ungranted.id),
            position=1,
        )
    )
    db.add(
        ProductCollectionItem(
            tenant_id=scope.tenant_id,
            storefront_id=scope.storefront_id,
            collection_id=int(collections[0].id),
            product_id=int(direct_offer_product.id),
            position=2,
        )
    )
    await db.commit()

    visible = await ProductCollectionCatalogAccess.visible_by_ids(
        db,
        tenant_scope=scope,
        product_ids=[int(ungranted.id), int(direct_offer_product.id)],
    )
    assert visible == {}
    resolved = await ProductCollectionResolver.resolve_placement(
        db,
        surface_key="yandex_business",
        slot_key="categories",
        tenant_scope=scope,
    )
    assert resolved["collections"] == []

    with pytest.raises(HTTPException) as rejected:
        await ManagerProductCollectionService.replace_items(
            db,
            int(collections[0].id),
            [{"product_id": int(ungranted.id), "is_pinned": True}],
            tenant_scope=scope,
            actor_username="tenant-a",
            actor_staff_user_id=None,
        )
    assert rejected.value.status_code == 404

    with pytest.raises(HTTPException) as rejected_direct_offer:
        await ManagerProductCollectionService.replace_items(
            db,
            int(collections[0].id),
            [{"product_id": int(direct_offer_product.id), "is_pinned": True}],
            tenant_scope=scope,
            actor_username="tenant-a",
            actor_staff_user_id=None,
        )
    assert rejected_direct_offer.value.status_code == 404
