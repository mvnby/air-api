from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from services.command_transaction import command_transaction


@pytest.fixture
async def transaction_session_factory(
    tmp_path: Path,
) -> AsyncIterator[Any]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'command_transaction.db'}",
        echo=False,
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE command_transaction_probe (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    value TEXT NOT NULL
                )
                """
            )
        )

    factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield factory
    await engine.dispose()


async def _stored_values(factory: Any) -> list[str]:
    async with factory() as session:
        result = await session.execute(
            text(
                """
                SELECT value
                FROM command_transaction_probe
                ORDER BY id
                """
            )
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_command_commits_after_read_only_autobegin(
    transaction_session_factory: Any,
):
    async with transaction_session_factory() as session:
        await session.execute(text("SELECT 1"))

        async with command_transaction(session):
            await session.execute(
                text(
                    """
                    INSERT INTO command_transaction_probe (value)
                    VALUES ('persisted')
                    """
                )
            )

    assert await _stored_values(transaction_session_factory) == ["persisted"]


@pytest.mark.asyncio
async def test_command_uses_savepoint_inside_explicit_uow(
    transaction_session_factory: Any,
):
    async with transaction_session_factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO command_transaction_probe (value)
                    VALUES ('before')
                    """
                )
            )

            with pytest.raises(RuntimeError, match="rollback nested command"):
                async with command_transaction(session):
                    await session.execute(
                        text(
                            """
                            INSERT INTO command_transaction_probe (value)
                            VALUES ('nested')
                            """
                        )
                    )
                    raise RuntimeError("rollback nested command")

            await session.execute(
                text(
                    """
                    INSERT INTO command_transaction_probe (value)
                    VALUES ('after')
                    """
                )
            )

    assert await _stored_values(transaction_session_factory) == ["before", "after"]


@pytest.mark.asyncio
async def test_failed_autobegin_command_preserves_preexisting_root_work(
    transaction_session_factory: Any,
):
    async with transaction_session_factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO command_transaction_probe (value)
                VALUES ('before')
                """
            )
        )

        with pytest.raises(RuntimeError, match="rollback command savepoint"):
            async with command_transaction(session):
                await session.execute(
                    text(
                        """
                        INSERT INTO command_transaction_probe (value)
                        VALUES ('nested')
                        """
                    )
                )
                raise RuntimeError("rollback command savepoint")

        await session.execute(
            text(
                """
                INSERT INTO command_transaction_probe (value)
                VALUES ('after')
                """
            )
        )
        await session.commit()

    assert await _stored_values(transaction_session_factory) == ["before", "after"]


@pytest.mark.asyncio
async def test_command_rolls_back_owned_autobegin_on_error(
    transaction_session_factory: Any,
):
    async with transaction_session_factory() as session:
        await session.execute(text("SELECT 1"))

        with pytest.raises(RuntimeError, match="rollback owned command"):
            async with command_transaction(session):
                await session.execute(
                    text(
                        """
                        INSERT INTO command_transaction_probe (value)
                        VALUES ('rolled-back')
                        """
                    )
                )
                raise RuntimeError("rollback owned command")

    assert await _stored_values(transaction_session_factory) == []


@pytest.mark.asyncio
async def test_nested_command_cannot_commit_outer_autobegin_scope(
    transaction_session_factory: Any,
):
    async with transaction_session_factory() as session:
        await session.execute(text("SELECT 1"))

        with pytest.raises(RuntimeError, match="rollback outer command"):
            async with command_transaction(session):
                await session.execute(
                    text(
                        """
                        INSERT INTO command_transaction_probe (value)
                        VALUES ('outer')
                        """
                    )
                )
                async with command_transaction(session):
                    await session.execute(
                        text(
                            """
                            INSERT INTO command_transaction_probe (value)
                            VALUES ('inner')
                            """
                        )
                    )
                raise RuntimeError("rollback outer command")

        await session.commit()

    assert await _stored_values(transaction_session_factory) == []
