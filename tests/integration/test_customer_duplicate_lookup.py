import asyncio
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event, insert, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.input_validation import normalize_phone_digits
from core.customer_duplicate_keys import (
    email_candidate_key,
    non_ascii_contact,
    phone_candidate_key,
    stripped_key,
)
from models import Customer
from models.tenancy import Tenant
from services.customer_creation_service import (
    CustomerAlreadyExistsError,
    CustomerCreationService,
)


async def find_duplicate(db, tenant_scope, **values):
    return await CustomerCreationService._find_duplicate(
        db,
        tenant_scope=tenant_scope,
        **dict(dict(phone=None, email=None, inn=None), **values),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored,incoming",
    [
        ("+375 (29) 111-22-33", "8 (029) 111-22-33"),
        ("0291112233", "291112233"),
        ("375291112233 доб. 456", "+375291112233"),
        ("80291112233 доб. 456", "+375291112233"),
        ("+7(495)123-45-67", "74951234567"),
        ("375291112233٤", "+375291112233"),
        ("٢٩١١١٢٢٣٣", "375٢٩١١١٢٢٣٣"),
        ("０２９１１１２２３３", "０２９１１１２２３３"),
    ],
)
async def test_duplicate_phone_preserves_normalization(
    db, tenant_scope, stored, incoming
):
    customer = Customer(tenant_id=1, name="Existing", phone=stored)
    db.add(customer)
    await db.flush()
    assert normalize_phone_digits(stored) == normalize_phone_digits(incoming)
    duplicate = await find_duplicate(db, tenant_scope, phone=incoming)
    assert duplicate and duplicate[0].id == customer.id and duplicate[1] == ("phone",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored,incoming",
    [
        ("\tOFFICE@example.test\u00a0", "office@EXAMPLE.TEST"),
        ("KNOWN@example.test", "known@example.test"),
        ("İ@example.test", "i\u0307@example.test"),
        ("ДИРЕКТОР@пример.рф", "директор@пример.рф"),
    ],
)
async def test_duplicate_email_preserves_python_lowercase(
    db, tenant_scope, stored, incoming
):
    customer = Customer(tenant_id=1, name="Existing", phone="", email=stored)
    db.add(customer)
    await db.flush()
    duplicate = await find_duplicate(db, tenant_scope, email=incoming)
    assert duplicate and duplicate[0].id == customer.id and duplicate[1] == ("email",)


@pytest.mark.asyncio
async def test_duplicate_ranking_ties_scope_and_archived(db, tenant_scope):
    other = Tenant(slug="other", display_name="Other")
    db.add(other)
    await db.flush()
    rows = [
        Customer(
            tenant_id=1,
            name="All",
            phone="291112233",
            email="a@example.test",
            inn="\u2007123456789\t",
            is_archived=True,
        ),
        Customer(
            tenant_id=1,
            name="Newer all",
            phone="80291112233",
            email="A@example.test",
            inn="123456789",
            is_archived=True,
        ),
        Customer(
            tenant_id=other.id,
            name="Other tenant",
            phone="291112233",
            email="a@example.test",
            inn="123456789",
        ),
        Customer(
            tenant_id=1,
            name="Phone email",
            phone="+375291112233",
            email="a@example.test",
        ),
        Customer(tenant_id=1, name="INN only", phone="", inn="123456789"),
    ]
    db.add_all(rows)
    await db.flush()
    values = dict(phone="+375291112233", email="a@example.test", inn="123456789")
    duplicate = await find_duplicate(db, tenant_scope, **values)
    assert duplicate[0].id == rows[1].id
    assert duplicate[1] == ("inn", "phone", "email")
    for row in rows[:2]:
        await db.delete(row)
    await db.flush()
    # INN (300) ties phone+email (300); latest id wins, as before.
    duplicate = await find_duplicate(db, tenant_scope, **values)
    assert duplicate[0].id == rows[-1].id and duplicate[1] == ("inn",)
    assert (
        await find_duplicate(
            db, tenant_scope, phone="999999999", email="none@example.test"
        )
        is None
    )
    assert await find_duplicate(db, tenant_scope, phone="", email=" ", inn=None) is None


@pytest.mark.asyncio
async def test_sql_candidates_are_confirmed_and_follow_updates(db, tenant_scope):
    # ASCII candidate key is intentionally a superset: Unicode digits still count
    # in Python and must not be silently stripped into a false duplicate.
    customer = Customer(tenant_id=1, name="Unicode phone", phone="٢+375291112233")
    db.add(customer)
    await db.flush()
    assert await find_duplicate(db, tenant_scope, phone="375291112233") is None
    await db.execute(
        text("UPDATE customer SET phone = '8 (029) 111-22-33' WHERE id = :id"),
        {"id": customer.id},
    )
    db.expire_all()
    duplicate = await find_duplicate(db, tenant_scope, phone="375291112233")
    assert duplicate and duplicate[1] == ("phone",)


@pytest.mark.asyncio
async def test_duplicate_lookup_loads_only_candidates_and_no_relationships(
    db, tenant_scope
):
    await db.execute(
        insert(Customer),
        [
            Customer(
                tenant_id=1,
                name=f"Synthetic {i}",
                phone=f"+37529{i:07}",
                email=f"u{i}@example.test",
                inn=str(100000000 + i),
            ).model_dump(exclude={"id"})
            for i in range(3000)
        ],
    )
    await db.execute(text("ANALYZE customer"))
    statements, loaded = [], []

    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    def capture_customer(customer, context):
        loaded.append(customer.id)

    connection = (await db.connection()).sync_connection
    event.listen(connection, "before_cursor_execute", capture)
    event.listen(Customer, "load", capture_customer)
    try:
        duplicate = await find_duplicate(
            db,
            tenant_scope,
            phone="8(029)0002999",
            email="U2999@example.test",
            inn="100002999",
        )
    finally:
        event.remove(connection, "before_cursor_execute", capture)
        event.remove(Customer, "load", capture_customer)
    assert duplicate and duplicate[0].name == "Synthetic 2999"
    assert len(statements) == 1
    assert loaded == [duplicate[0].id]
    for field, predicate in (
        ("phone", phone_candidate_key(Customer.phone) == "375290002999"),
        ("email", email_candidate_key(Customer.email) == "u2999@example.test"),
        ("inn", stripped_key(Customer.inn) == "100002999"),
        ("phone_unicode", non_ascii_contact(Customer.phone)),
        ("email_unicode", non_ascii_contact(Customer.email)),
    ):
        query = select(Customer.id).where(Customer.tenant_id == 1, predicate)
        compiled = query.compile(
            dialect=db.get_bind().dialect, compile_kwargs={"literal_binds": True}
        )
        plan = (await db.execute(text("EXPLAIN " + str(compiled)))).scalars().all()
        assert f"ix_customer_duplicate_{field}" in "\n".join(plan)


@pytest.mark.asyncio
async def test_duplicate_index_migration_roundtrip_matches_metadata(db_engine):
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/cust20261023dedup01_customer_duplicate_indexes.py"
    )
    spec = importlib.util.spec_from_file_location("customer_duplicate_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def roundtrip(connection):
        index_query = text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'customer' AND indexname LIKE 'ix_customer_duplicate_%' ORDER BY indexname"
        )
        expected = connection.execute(index_query).all()
        connection.commit()
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            with context.begin_transaction():
                migration.downgrade()
                migration.upgrade()
                migration.upgrade()
        assert connection.execute(index_query).all() == expected
        assert len(expected) == 5

    async with db_engine.connect() as connection:
        await connection.run_sync(roundtrip)


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_first", [True, False])
async def test_duplicate_guard_serializes_same_tenant_creates(
    db_engine, tenant_scope, commit_first
):
    first = AsyncSession(db_engine, expire_on_commit=False)
    second = AsyncSession(db_engine, expire_on_commit=False)
    pending = None
    try:
        created = await CustomerCreationService.create_record_for_manager(
            first,
            payload={"name": "First", "phone": "8(029)1112233"},
            tenant_scope=tenant_scope,
        )

        async def create_second():
            async with second.begin():
                return await CustomerCreationService.create_record_for_manager(
                    second,
                    payload={"name": "Second", "phone": "+375291112233"},
                    tenant_scope=tenant_scope,
                )

        pending = asyncio.create_task(create_second())
        # Observe PostgreSQL's actual advisory-lock wait, not just a short sleep.
        async with AsyncSession(db_engine) as observer:
            for _ in range(100):
                waiting = await observer.scalar(
                    text(
                        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
                    )
                )
                if waiting:
                    break
                await asyncio.sleep(0.01)
            assert waiting == 1
        if commit_first:
            await first.commit()
            with pytest.raises(CustomerAlreadyExistsError) as error:
                await asyncio.wait_for(pending, timeout=5)
            assert error.value.customer_id == created.id
        else:
            await first.rollback()
            assert (await asyncio.wait_for(pending, timeout=5)).name == "Second"
        async with AsyncSession(db_engine) as observer:
            customers = (await observer.execute(select(Customer))).scalars().all()
            assert len(customers) == 1
    finally:
        await first.rollback()
        if pending and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await first.close()
        await second.close()
