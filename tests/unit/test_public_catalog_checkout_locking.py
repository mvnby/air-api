import pytest
from sqlalchemy.dialects import postgresql

from crud.public_catalog import PublicCatalogDAO
from models.tenancy import TenantScope


class _Result:
    def all(self):
        return []


class _CapturingSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _Result()


def _postgres_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


@pytest.mark.asyncio
async def test_shared_checkout_prices_use_deterministic_compatible_row_locks():
    session = _CapturingSession()

    result = await PublicCatalogDAO.get_shared_prices_by_ids(
        session,
        product_ids={9, 3},
    )

    sql = _postgres_sql(session.statement)
    assert result == {}
    assert "ORDER BY product.id ASC" in sql
    assert "FOR SHARE OF product" in sql
    assert "FOR UPDATE" not in sql


@pytest.mark.asyncio
async def test_offer_checkout_prices_share_lock_product_and_offer_in_id_order():
    session = _CapturingSession()

    result = await PublicCatalogDAO.get_offer_prices_by_ids(
        session,
        tenant_scope=TenantScope(tenant_id=7, storefront_id=11),
        product_ids={9, 3},
    )

    sql = _postgres_sql(session.statement)
    assert result == {}
    assert "ORDER BY product.id ASC" in sql
    assert "FOR SHARE OF product, tenant_offer" in sql
    assert "FOR UPDATE" not in sql
