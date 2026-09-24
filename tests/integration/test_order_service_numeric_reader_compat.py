"""The deployed reader must survive the later INTEGER -> NUMERIC schema expansion."""

from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import (
    Installer,
    Order,
    OrderInstaller,
    OrderProposal,
    OrderServiceLink,
    Payment,
    PaymentCurrency,
)
from schemas_manager_orders import OrderServiceLineResponse
from services.documents.standard import GeneralDocStrategy
from services.order_projection_service import OrderProjectionService
from services.order_transfer_service import OrderTransferService


@pytest.mark.asyncio
@pytest.mark.parametrize("numeric_schema", [False, True], ids=["current-integer", "future-numeric"])
async def test_order_reader_survives_service_money_schema_expansion(db_engine, numeric_schema):
    # PostgreSQL DDL is transactional. One connection sees the future schema;
    # rolling back leaves this worker's normal test schema untouched.
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            if numeric_schema:
                await connection.execute(text("""
                    ALTER TABLE order_service_link
                    ALTER COLUMN price TYPE NUMERIC USING price::numeric,
                    ALTER COLUMN cost TYPE NUMERIC USING cost::numeric
                """))

            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                order = Order(
                    tenant_id=1,
                    storefront_id=1,
                    target_currency=PaymentCurrency.USD,
                    target_currency_amount=100,
                )
                installer = Installer(name="Mixed-version installer")
                session.add_all([order, installer])
                await session.flush()

                proposal = OrderProposal(order_id=order.id, is_selected=True)
                session.add(proposal)
                await session.flush()
                session.add_all([
                    OrderServiceLink(
                        order_id=order.id, proposal_id=proposal.id,
                        title="Монтаж", quantity=2, price=100, cost=50,
                    ),
                    OrderInstaller(order_id=order.id, installer_id=installer.id, agreed_pay=25.0),
                    Payment(order_id=order.id, amount=20.0, currency=PaymentCurrency.BYN),
                    Payment(order_id=order.id, amount=10.0, currency=PaymentCurrency.USD),
                ])
                await session.commit()
                session.expunge_all()

                result = await session.execute(
                    select(Order).where(Order.id == order.id).options(
                        selectinload(Order.proposals),
                        selectinload(Order.product_links),
                        selectinload(Order.service_links),
                        selectinload(Order.installers),
                        selectinload(Order.payments),
                    )
                )
                loaded = result.scalar_one()
                line = loaded.service_links[0]
                assert isinstance(line.price, Decimal if numeric_schema else int)
                assert isinstance(line.cost, Decimal if numeric_schema else int)

                loaded.calculate_totals()
                assert loaded.total_amount == 200.0
                assert loaded.total_cost == 125.0
                assert loaded.margin == 75.0
                assert loaded.total_payments == 40.0
                assert loaded.target_currency_payments == 20.0
                assert loaded.balance_due == 160.0

                api_line = OrderServiceLineResponse.model_validate(
                    OrderProjectionService._map_service_line(line)
                )
                assert api_line.price == 100.0
                assert api_line.cost == 50.0
                assert api_line.line_total == 200.0

                transfer_line = OrderTransferService._service_line_snapshot(line)
                assert transfer_line.price == 100
                assert transfer_line.cost == 50

                strategy = GeneralDocStrategy(session, loaded.id)
                strategy.order = loaded
                rows = strategy._prepare_table_data()
                assert rows[0][-1] == "200.00"
                assert rows[-1][-1] == "200.00"
        finally:
            await transaction.rollback()
