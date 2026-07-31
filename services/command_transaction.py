"""Shared transaction boundary for composable application commands."""

from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction


def command_transaction(session: AsyncSession) -> AsyncSessionTransaction:
    """Own a root transaction, or a SAVEPOINT inside an explicit caller UoW."""
    if session.in_transaction():
        return session.begin_nested()
    return session.begin()
