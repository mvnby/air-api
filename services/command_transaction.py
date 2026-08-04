"""Shared transaction boundary for composable application commands."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import SessionTransactionOrigin


@asynccontextmanager
async def command_transaction(session: AsyncSession) -> AsyncIterator[None]:
    """Own the root transaction unless the caller opened an explicit UoW."""
    transaction = session.get_transaction()
    if transaction is None:
        async with session.begin():
            yield
        return

    origin = transaction.sync_transaction.origin
    if origin is SessionTransactionOrigin.AUTOBEGIN:
        # Authentication and other read dependencies trigger SQLAlchemy's
        # implicit AUTOBEGIN. The command owns that root transaction and must
        # finish it, otherwise session.close() rolls the successful write back.
        try:
            yield
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()
        return

    async with session.begin_nested():
        yield
