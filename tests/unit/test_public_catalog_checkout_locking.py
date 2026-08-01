import pytest
from sqlalchemy.dialects import postgresql

from crud.public_catalog_checkout import (
    LockedPublicCatalogProduct,
    PublicCatalogCheckoutDAO,
)
from models.tenancy import TenantScope


class _Result:
    def __init__(self, rows=()):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _CapturingSession:
    def __init__(self, rows=()):
        self.statement = None
        self.rows = rows

    async def execute(self, statement):
        self.statement = statement
        return _Result(self.rows)


def _postgres_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


@pytest.mark.asyncio
async def test_shared_checkout_snapshot_locks_title_price_and_context_currency():
    session = _CapturingSession([(3, "Model 03", 3200, "BYN")])

    result = await PublicCatalogCheckoutDAO.get_shared_snapshots_by_ids(
        session,
        tenant_scope=TenantScope(
            tenant_id=7,
            storefront_id=11,
            is_canonical_storefront=True,
        ),
        product_ids={9, 3},
    )

    sql = _postgres_sql(session.statement)
    assert result == {
        3: LockedPublicCatalogProduct(
            product_id=3,
            title="Model 03",
            unit_price=3200,
            currency="BYN",
        )
    }
    assert "product.title" in sql
    assert "storefront.currency" in sql
    assert "storefront.id = 11" in sql
    assert "storefront.tenant_id = 7" in sql
    assert "storefront.status = 'active'" in sql
    assert "ORDER BY product.id ASC" in sql
    assert "FOR SHARE OF product, storefront" in sql
    assert "FOR UPDATE" not in sql


@pytest.mark.asyncio
async def test_offer_checkout_snapshot_locks_exact_scope_in_product_order():
    session = _CapturingSession()

    result = await PublicCatalogCheckoutDAO.get_offer_snapshots_by_ids(
        session,
        tenant_scope=TenantScope(
            tenant_id=7,
            storefront_id=11,
            is_canonical_storefront=False,
        ),
        product_ids={9, 3},
    )

    sql = _postgres_sql(session.statement)
    assert result == {}
    assert "tenant_offer.tenant_id = 7" in sql
    assert "tenant_offer.storefront_id = 11" in sql
    assert "product.title" in sql
    assert "storefront.currency" in sql
    assert "ORDER BY product.id ASC" in sql
    assert "FOR SHARE OF product, tenant_offer, storefront" in sql
    assert "FOR UPDATE" not in sql
