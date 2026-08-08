"""Shared transaction boundary for composable application commands."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import SessionTransactionOrigin


_COMMAND_TRANSACTION_DEPTH_KEY = "mvn_command_transaction_depth"


@asynccontextmanager
async def command_transaction(session: AsyncSession) -> AsyncIterator[None]:
    """Commit command-owned roots and isolate work inside caller transactions."""
    depth = int(session.info.get(_COMMAND_TRANSACTION_DEPTH_KEY, 0) or 0)
    session.info[_COMMAND_TRANSACTION_DEPTH_KEY] = depth + 1
    try:
        if depth > 0:
            # A composed command never owns the root transaction. Its caller
            # decides whether the complete unit of work is committed.
            async with session.begin_nested():
                yield
            return

        transaction = session.get_transaction()
        if transaction is None:
            await session.begin()
            try:
                yield
            except BaseException:
                await session.rollback()
                raise
            else:
                # Commit through AsyncSession so acknowledgement-loss handling
                # and session instrumentation observe the real commit boundary.
                # A commit exception is deliberately not followed by rollback:
                # the database may already have made the transaction durable.
                await session.commit()
            return

        origin = transaction.sync_transaction.origin
        if origin is SessionTransactionOrigin.AUTOBEGIN:
            # Authentication and other read dependencies trigger SQLAlchemy's
            # implicit AUTOBEGIN. Isolate the command in a SAVEPOINT so a failed
            # command does not roll back work that predates it on a reused
            # session. A successful outer command still owns and commits the
            # implicit root.
            async with session.begin_nested():
                yield
            await session.commit()
            return

        async with session.begin_nested():
            yield
    finally:
        if depth > 0:
            session.info[_COMMAND_TRANSACTION_DEPTH_KEY] = depth
        else:
            session.info.pop(_COMMAND_TRANSACTION_DEPTH_KEY, None)
