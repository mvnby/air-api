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
    def __init__(self, rows=(), *, currency="BYN"):
        self.statements = []
        self.rows = rows
        self.currency = currency

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.currency

    async def execute(self, statement):
        self.statements.append(statement)
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
    session = _CapturingSession([(3, "Model 03", 3200)])

    result = await PublicCatalogCheckoutDAO.get_shared_snapshots_by_ids(
        session,
        tenant_scope=TenantScope(
            tenant_id=7,
            storefront_id=11,
            is_canonical_storefront=True,
        ),
        product_ids={9, 3},
    )

    storefront_sql, product_sql = map(_postgres_sql, session.statements)
    assert result == {
        3: LockedPublicCatalogProduct(
            product_id=3,
            title="Model 03",
            unit_price=3200,
            currency="BYN",
        )
    }
    assert "storefront.currency" in storefront_sql
    assert "storefront.id = 11" in storefront_sql
    assert "storefront.tenant_id = 7" in storefront_sql
    assert "storefront.status = 'active'" in storefront_sql
    assert "FOR SHARE OF storefront" in storefront_sql
    assert "product.title" in product_sql
    assert "ORDER BY product.id ASC" in product_sql
    assert "FOR SHARE OF product" in product_sql
    assert "storefront" not in product_sql


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

    storefront_sql, offer_sql = map(_postgres_sql, session.statements)
    assert result == {}
    assert "storefront.currency" in storefront_sql
    assert "FOR SHARE OF storefront" in storefront_sql
    assert "tenant_offer.tenant_id = 7" in offer_sql
    assert "tenant_offer.storefront_id = 11" in offer_sql
    assert "product.title" in offer_sql
    assert "ORDER BY product.id ASC" in offer_sql
    assert "FOR SHARE OF product, tenant_offer" in offer_sql
    assert " JOIN storefront" not in offer_sql
    assert "storefront.currency" not in offer_sql


@pytest.mark.asyncio
async def test_inactive_storefront_stops_before_product_locks():
    session = _CapturingSession(currency=None)

    result = await PublicCatalogCheckoutDAO.get_offer_snapshots_by_ids(
        session,
        tenant_scope=TenantScope(
            tenant_id=7,
            storefront_id=11,
            is_canonical_storefront=False,
        ),
        product_ids={3},
    )

    assert result == {}
    assert len(session.statements) == 1
    assert "FOR SHARE OF storefront" in _postgres_sql(session.statements[0])
