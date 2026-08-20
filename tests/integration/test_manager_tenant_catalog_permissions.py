from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.security import create_access_token
from models import (
    Brand,
    Customer,
    CustomerEquipment,
    EquipmentComponent,
    Product,
    ProductCollection,
    ProductSeries,
    StaffUser,
    Storefront,
    Supplier,
    Tenant,
    TenantCatalogGrant,
    TenantMembership,
    TenantOffer,
)


async def _create_tenant_manager(
    session: AsyncSession,
) -> tuple[StaffUser, Tenant, Storefront, Storefront]:
    tenant = Tenant(
        slug="polotsk-test",
        display_name="Dvina Climate",
        status="active",
        is_system=False,
    )
    session.add(tenant)
    await session.flush()
    storefront = Storefront(
        tenant_id=int(tenant.id),
        slug="main",
        display_name="Dvina Climate",
        status="active",
        is_default=True,
    )
    other_storefront = Storefront(
        tenant_id=int(tenant.id),
        slug="other",
        display_name="Other storefront",
        status="active",
        is_default=False,
    )
    user = StaffUser(
        display_name="Polotsk Manager",
        status="active",
        roles=["manager"],
        primary_role="manager",
        username="polotsk-manager-test",
    )
    session.add_all([storefront, other_storefront, user])
    await session.flush()
    session.add(
        TenantMembership(
            tenant_id=int(tenant.id),
            staff_user_id=int(user.id),
            role="manager",
            status="active",
        )
    )
    await session.flush()
    return user, tenant, storefront, other_storefront


def _headers(user: StaffUser) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "staff_user_id": user.id,
            "auth_version": user.auth_version,
            "auth_source": "tenant-catalog-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_tenant_catalog_is_published_supplier_free_and_exactly_storefront_scoped(
    async_client: AsyncClient,
    db: AsyncSession,
):
    user, tenant, storefront, other_storefront = await _create_tenant_manager(db)
    brand = Brand(title="Safe Brand", slug="safe-brand", is_published=True)
    db.add(brand)
    await db.flush()
    series = ProductSeries(
        brand_id=int(brand.id),
        title="Safe Series",
        slug="safe-series",
        is_published=True,
    )
    db.add(series)
    await db.flush()
    allowed_product = Product(
        title="Allowed Model",
        slug="allowed-model",
        brand_id=int(brand.id),
        series_id=int(series.id),
        price=1700,
        is_published=True,
        source_url="https://supplier.example/secret",
    )
    foreign_offer_product = Product(
        title="Foreign Offer Model",
        slug="foreign-offer-model",
        price=1800,
        is_published=True,
    )
    disabled_product = Product(
        title="Disabled Offer Model",
        slug="disabled-offer-model",
        price=1900,
        is_published=True,
    )
    unpublished_product = Product(
        title="Unpublished Model",
        slug="unpublished-model",
        price=2000,
        is_published=False,
    )
    db.add_all(
        [
            allowed_product,
            foreign_offer_product,
            disabled_product,
            unpublished_product,
        ]
    )
    await db.flush()
    db.add_all(
        [
            TenantOffer(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                product_id=int(allowed_product.id),
                price=1750,
                is_published=True,
                status="active",
                created_by_username="system:test",
                updated_by_username="system:test",
            ),
            TenantOffer(
                tenant_id=int(tenant.id),
                storefront_id=int(other_storefront.id),
                product_id=int(foreign_offer_product.id),
                price=1850,
                is_published=True,
                status="active",
                created_by_username="system:test",
                updated_by_username="system:test",
            ),
            TenantOffer(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                product_id=int(disabled_product.id),
                price=1950,
                is_published=True,
                status="disabled",
                created_by_username="system:test",
                updated_by_username="system:test",
            ),
            TenantOffer(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                product_id=int(unpublished_product.id),
                price=2050,
                is_published=True,
                status="active",
                created_by_username="system:test",
                updated_by_username="system:test",
            ),
        ]
    )
    await db.commit()

    response = await async_client.get(
        "/api/manager/tenant-catalog/products",
        headers=_headers(user),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    by_slug = {item["slug"]: item for item in payload["items"]}
    assert set(by_slug) == {
        "allowed-model",
        "foreign-offer-model",
        "disabled-offer-model",
    }
    assert by_slug["allowed-model"] == {
        "id": allowed_product.id,
        "title": "Allowed Model",
        "slug": "allowed-model",
        "brand_title": "Safe Brand",
        "series_title": "Safe Series",
        "main_image": None,
        "product_kind": "unknown",
        "is_inverter": False,
        "power_cooling": None,
        "offer_id": by_slug["allowed-model"]["offer_id"],
        "offer_status": "active",
        "offer_is_published": True,
        "effective_price": 1750,
        "allowed": True,
    }
    assert by_slug["foreign-offer-model"]["offer_id"] is None
    assert by_slug["foreign-offer-model"]["effective_price"] is None
    assert by_slug["foreign-offer-model"]["allowed"] is False
    assert by_slug["disabled-offer-model"]["offer_status"] == "disabled"
    assert by_slug["disabled-offer-model"]["effective_price"] is None
    assert by_slug["disabled-offer-model"]["allowed"] is False

    prohibited_fields = {
        "price",
        "old_price",
        "source_url",
        "supplier_id",
        "min_cost_byn",
        "recommended_price_byn",
        "margin_abs_preview",
        "margin_pct_preview",
        "vitebsk_qty",
        "minsk_qty",
        "availability_status",
    }
    assert not prohibited_fields.intersection(by_slug["allowed-model"])

    allowed_only = await async_client.get(
        "/api/manager/tenant-catalog/products",
        headers=_headers(user),
        params={"allowed": "true"},
    )
    assert allowed_only.status_code == 200
    assert [item["slug"] for item in allowed_only.json()["items"]] == [
        "allowed-model"
    ]

    for legacy_path in (
        "/api/manager/products/list",
        "/api/manager/products/smart-search?q=Allowed",
        f"/api/manager/products/{allowed_product.id}",
    ):
        denied = await async_client.get(legacy_path, headers=_headers(user))
        assert denied.status_code == 403, legacy_path


@pytest.mark.asyncio
async def test_tenant_catalog_hides_grant_offer_until_exact_grant_is_active(
    async_client: AsyncClient,
    db: AsyncSession,
):
    user, tenant, storefront, other_storefront = await _create_tenant_manager(db)
    scoped_product = Product(
        title="Grant Scoped Model",
        slug="grant-scoped-model",
        price=3100,
        is_published=True,
    )
    cross_scope_product = Product(
        title="Cross Scope Grant Model",
        slug="cross-scope-grant-model",
        price=3200,
        is_published=True,
    )
    db.add_all([scoped_product, cross_scope_product])
    await db.flush()
    scoped_grant = TenantCatalogGrant(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        status="syncing",
        created_by_username="system:test",
        updated_by_username="system:test",
    )
    cross_scope_grant = TenantCatalogGrant(
        tenant_id=int(tenant.id),
        storefront_id=int(other_storefront.id),
        status="active",
        created_by_username="system:test",
        updated_by_username="system:test",
    )
    db.add_all([scoped_grant, cross_scope_grant])
    await db.flush()
    scoped_offer = TenantOffer(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        product_id=int(scoped_product.id),
        catalog_grant_id=int(scoped_grant.id),
        price=3150,
        is_published=True,
        status="active",
        price_source="inherited_master",
        created_by_username="system:test",
        updated_by_username="system:test",
    )
    cross_scope_offer = TenantOffer(
        tenant_id=int(tenant.id),
        storefront_id=int(other_storefront.id),
        product_id=int(cross_scope_product.id),
        catalog_grant_id=int(cross_scope_grant.id),
        price=3250,
        is_published=True,
        status="active",
        price_source="inherited_master",
        created_by_username="system:test",
        updated_by_username="system:test",
    )
    db.add_all([scoped_offer, cross_scope_offer])
    await db.commit()

    async def catalog_items(*, allowed: bool | None = None) -> dict[str, dict]:
        params = {} if allowed is None else {"allowed": str(allowed).lower()}
        response = await async_client.get(
            "/api/manager/tenant-catalog/products",
            headers=_headers(user),
            params=params,
        )
        assert response.status_code == 200, response.text
        return {item["slug"]: item for item in response.json()["items"]}

    async def assert_grant_offers_hidden() -> None:
        items = await catalog_items()
        for slug in ("grant-scoped-model", "cross-scope-grant-model"):
            assert items[slug]["offer_id"] is None
            assert items[slug]["offer_status"] is None
            assert items[slug]["offer_is_published"] is None
            assert items[slug]["effective_price"] is None
            assert items[slug]["allowed"] is False
        assert await catalog_items(allowed=True) == {}

    await assert_grant_offers_hidden()

    scoped_grant.status = "disabled"
    db.add(scoped_grant)
    await db.commit()
    await assert_grant_offers_hidden()

    scoped_grant.status = "active"
    db.add(scoped_grant)
    await db.commit()
    items = await catalog_items()
    assert items["grant-scoped-model"]["offer_id"] == scoped_offer.id
    assert items["grant-scoped-model"]["offer_status"] == "active"
    assert items["grant-scoped-model"]["offer_is_published"] is True
    assert items["grant-scoped-model"]["effective_price"] == 3150
    assert items["grant-scoped-model"]["allowed"] is True
    assert items["cross-scope-grant-model"]["offer_id"] is None
    assert items["cross-scope-grant-model"]["allowed"] is False
    assert list(await catalog_items(allowed=True)) == ["grant-scoped-model"]


@pytest.mark.asyncio
async def test_system_tenant_catalog_keeps_canonical_master_behavior(
    async_client: AsyncClient,
    db: AsyncSession,
):
    system_user = StaffUser(
        display_name="System Catalog Manager",
        status="active",
        roles=["manager"],
        primary_role="manager",
        username="system-catalog-manager-test",
    )
    product = Product(
        title="Canonical System Model",
        slug="canonical-system-model",
        price=4100,
        is_published=True,
    )
    db.add_all([system_user, product])
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(system_user.id),
            role="manager",
            status="active",
        )
    )
    await db.commit()

    response = await async_client.get(
        "/api/manager/tenant-catalog/products",
        headers=_headers(system_user),
        params={"search": "Canonical System Model", "allowed": "true"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {
            "id": product.id,
            "title": "Canonical System Model",
            "slug": "canonical-system-model",
            "brand_title": None,
            "series_title": None,
            "main_image": None,
            "product_kind": "unknown",
            "is_inverter": False,
            "power_cooling": None,
            "offer_id": None,
            "offer_status": None,
            "offer_is_published": None,
            "effective_price": 4100,
            "allowed": True,
        }
    ]


@pytest.mark.asyncio
async def test_non_system_tenant_cannot_mutate_offer_or_equipment_supplier_fields(
    async_client: AsyncClient,
    db: AsyncSession,
):
    user, tenant, storefront, _ = await _create_tenant_manager(db)
    product = Product(
        title="Protected Offer Model",
        slug="protected-offer-model",
        price=1000,
        is_published=True,
    )
    customer = Customer(
        tenant_id=int(tenant.id),
        name="Polotsk Customer",
        phone="+375291110099",
    )
    supplier = Supplier(name="Sensitive Supplier", code="sensitive-supplier")
    system_user = StaffUser(
        display_name="System Manager",
        status="active",
        roles=["manager"],
        primary_role="manager",
        username="system-equipment-manager-test",
    )
    system_customer = Customer(
        tenant_id=1,
        name="System Customer",
        phone="+375291110098",
    )
    db.add_all([product, customer, supplier, system_user, system_customer])
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(system_user.id),
            role="manager",
            status="active",
        )
    )
    offer = TenantOffer(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        product_id=int(product.id),
        price=1100,
        is_published=True,
        status="active",
        created_by_username="system:test",
        updated_by_username="system:test",
    )
    equipment = CustomerEquipment(customer_id=int(customer.id), display_name="Split")
    system_equipment = CustomerEquipment(
        customer_id=int(system_customer.id),
        display_name="System Split",
    )
    db.add_all([offer, equipment, system_equipment])
    await db.flush()
    component = EquipmentComponent(
        equipment_id=int(equipment.id),
        title="Existing component",
        supplier_id=int(supplier.id),
        supplier_invoice_number="TENANT-SECRET-INV",
        supplier_invoice_date=datetime(2026, 8, 1),
    )
    system_component = EquipmentComponent(
        equipment_id=int(system_equipment.id),
        title="System component",
        supplier_id=int(supplier.id),
        supplier_invoice_number="SYSTEM-VISIBLE-INV",
        supplier_invoice_date=datetime(2026, 8, 2),
    )
    db.add_all([component, system_component])
    await db.commit()
    headers = _headers(user)

    tenant_detail = await async_client.get(
        f"/api/manager/equipment/{equipment.id}",
        headers=headers,
    )
    assert tenant_detail.status_code == 200, tenant_detail.text
    tenant_component = tenant_detail.json()["components"][0]
    assert tenant_component["supplier_id"] is None
    assert tenant_component["supplier_invoice_number"] is None
    assert tenant_component["supplier_invoice_date"] is None

    tenant_safe_patch = await async_client.patch(
        f"/api/manager/equipment/{equipment.id}/components/{component.id}",
        headers=headers,
        json={"title": "Tenant-visible title"},
    )
    assert tenant_safe_patch.status_code == 200, tenant_safe_patch.text
    assert tenant_safe_patch.json()["supplier_id"] is None
    assert tenant_safe_patch.json()["supplier_invoice_number"] is None
    assert tenant_safe_patch.json()["supplier_invoice_date"] is None

    system_detail = await async_client.get(
        f"/api/manager/equipment/{system_equipment.id}",
        headers=_headers(system_user),
    )
    assert system_detail.status_code == 200, system_detail.text
    visible_system_component = system_detail.json()["components"][0]
    assert visible_system_component["supplier_id"] == supplier.id
    assert visible_system_component["supplier_invoice_number"] == "SYSTEM-VISIBLE-INV"
    assert visible_system_component["supplier_invoice_date"].startswith("2026-08-02")

    create_offer = await async_client.post(
        "/api/manager/tenant-offers",
        headers=headers,
        json={"product_id": product.id, "price": 1},
    )
    patch_offer = await async_client.patch(
        f"/api/manager/tenant-offers/{offer.id}",
        headers=headers,
        json={"price": 1},
    )
    create_component = await async_client.post(
        f"/api/manager/equipment/{equipment.id}/components",
        headers=headers,
        json={"title": "Denied", "supplier_id": 999999},
    )
    patch_component = await async_client.patch(
        f"/api/manager/equipment/{equipment.id}/components/{component.id}",
        headers=headers,
        json={"supplier_invoice_number": "SECRET-INV"},
    )
    create_equipment = await async_client.post(
        "/api/manager/equipment",
        headers=headers,
        json={"customer_id": customer.id, "supplier_id": 999999},
    )
    create_from_order = await async_client.post(
        "/api/manager/equipment/from-order/999999",
        headers=headers,
        json={"supplier_id": 999999},
    )

    assert create_offer.status_code == 403
    assert patch_offer.status_code == 403
    assert create_component.status_code == 403
    assert patch_component.status_code == 403
    assert create_equipment.status_code == 403
    assert create_from_order.status_code == 403

    await db.refresh(offer)
    await db.refresh(component)
    assert offer.price == 1100
    assert component.supplier_id == supplier.id
    assert component.supplier_invoice_number == "TENANT-SECRET-INV"
    components = list(
        (
            await db.execute(
                select(EquipmentComponent).where(
                    EquipmentComponent.equipment_id == equipment.id
                )
            )
        ).scalars()
    )
    assert [item.id for item in components] == [component.id]


@pytest.mark.asyncio
async def test_tenant_manager_me_exposes_only_minimal_server_capabilities(
    async_client: AsyncClient,
    db: AsyncSession,
):
    user, tenant, storefront, _ = await _create_tenant_manager(db)
    await db.commit()

    response = await async_client.get("/api/manager/me", headers=_headers(user))

    assert response.status_code == 200
    assert response.json()["tenant_id"] == tenant.id
    assert response.json()["storefront_id"] == storefront.id
    assert response.json()["is_system_tenant"] is False
    assert response.json()["capabilities"] == [
        "crm.manage",
        "catalog.master.read",
        "storefront.offers.read",
        "storefront.collections.manage",
    ]

    listed = await async_client.get(
        "/api/manager/product-collections",
        headers=_headers(user),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json() == {"items": []}

    created = await async_client.post(
        "/api/manager/product-collections",
        headers=_headers(user),
        json={
            "internal_name": "Tenant-owned selection",
            "public_title": "Tenant-owned selection",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["tenant_id"] == tenant.id
    assert created.json()["storefront_id"] == storefront.id


@pytest.mark.asyncio
async def test_tenant_manager_cannot_write_or_read_internal_stock_collection_rules(
    async_client: AsyncClient,
    db: AsyncSession,
):
    user, tenant, storefront, _ = await _create_tenant_manager(db)
    legacy = ProductCollection(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        slug="legacy-stock-rule",
        internal_name="Legacy stock rule",
        public_title="Legacy stock rule",
        mode="automatic",
        rule_config={
            "product_kinds": ["complete_split_system"],
            "public_stock_states": ["supplier_stock"],
        },
    )
    db.add(legacy)
    await db.commit()
    headers = _headers(user)

    legacy_response = await async_client.get(
        f"/api/manager/product-collections/{legacy.id}",
        headers=headers,
    )
    assert legacy_response.status_code == 200, legacy_response.text
    assert legacy_response.json()["rule_config"]["product_kinds"] == [
        "complete_split_system"
    ]
    assert legacy_response.json()["rule_config"]["public_stock_states"] == []

    denied_create = await async_client.post(
        "/api/manager/product-collections",
        headers=headers,
        json={
            "internal_name": "Denied stock rule",
            "public_title": "Denied stock rule",
            "mode": "automatic",
            "rule_config": {"public_stock_states": ["local_stock"]},
        },
    )
    assert denied_create.status_code == 403, denied_create.text

    safe_create = await async_client.post(
        "/api/manager/product-collections",
        headers=headers,
        json={
            "internal_name": "Safe tenant rule",
            "public_title": "Safe tenant rule",
            "mode": "automatic",
            "rule_config": {"product_kinds": ["complete_split_system"]},
        },
    )
    assert safe_create.status_code == 200, safe_create.text
    safe_id = safe_create.json()["id"]

    denied_update = await async_client.patch(
        f"/api/manager/product-collections/{safe_id}",
        headers=headers,
        json={"rule_config": {"public_stock_states": ["out_of_stock"]}},
    )
    assert denied_update.status_code == 403, denied_update.text
    unchanged = await async_client.get(
        f"/api/manager/product-collections/{safe_id}",
        headers=headers,
    )
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["rule_config"]["product_kinds"] == [
        "complete_split_system"
    ]
    assert unchanged.json()["rule_config"]["public_stock_states"] == []
