from sqlalchemy.dialects import postgresql
from sqlmodel import select

from models import Product, TenantOffer
from models.tenancy import TenantScope
from services.manager_tenant_catalog_service import ManagerTenantCatalogService


def _offer_join_sql(tenant_scope: TenantScope) -> str:
    statement = select(Product.id).outerjoin(
        TenantOffer,
        ManagerTenantCatalogService._offer_join(tenant_scope),
    )
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_tenant_offer_join_requires_exact_active_catalog_grant():
    sql = _offer_join_sql(
        TenantScope(
            tenant_id=7,
            storefront_id=11,
            is_system=False,
            is_canonical_storefront=False,
        )
    )

    assert "tenant_offer.tenant_id = 7" in sql
    assert "tenant_offer.storefront_id = 11" in sql
    assert "tenant_offer.catalog_grant_id IS NULL" in sql
    assert "tenant_catalog_grant.id = tenant_offer.catalog_grant_id" in sql
    assert "tenant_catalog_grant.tenant_id = 7" in sql
    assert "tenant_catalog_grant.storefront_id = 11" in sql
    assert "tenant_catalog_grant.status = 'active'" in sql


def test_system_offer_join_preserves_canonical_behavior_without_grant_fence():
    sql = _offer_join_sql(
        TenantScope(
            tenant_id=1,
            storefront_id=1,
            is_system=True,
            is_canonical_storefront=True,
        )
    )

    assert "tenant_offer.tenant_id = 1" in sql
    assert "tenant_offer.storefront_id = 1" in sql
    assert "tenant_catalog_grant" not in sql
