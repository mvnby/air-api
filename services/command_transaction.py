"""Shared transaction boundary for composable application commands."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import SessionTransactionOrigin


@asynccontextmanager
async def command_transaction(session: AsyncSession) -> AsyncIterator[None]:
    """Commit command-owned roots and isolate work inside caller transactions."""
    transaction = session.get_transaction()
    if transaction is None:
        async with session.begin():
            yield
        return

    origin = transaction.sync_transaction.origin
    if origin is SessionTransactionOrigin.AUTOBEGIN:
        # Authentication and other read dependencies trigger SQLAlchemy's
        # implicit AUTOBEGIN. Isolate the command in a SAVEPOINT so a failed
        # command does not roll back work that predates it on a reused session.
        # A successful command still owns and commits the implicit root.
        async with session.begin_nested():
            yield
        await session.commit()
        return

    async with session.begin_nested():
        yield
