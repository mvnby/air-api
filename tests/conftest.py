import os

# Apply test-safe process settings before any application/config module can be
# imported during collection. Local .env notification credentials must never be
# inherited by tests.
os.environ.update(
    {
        "ENVIRONMENT": "test",
        # Keep collection hermetic in clean worktrees: application settings
        # intentionally require these values, but tests must not depend on a
        # developer's .env or inherit real credentials.
        "SECRET_KEY": "test-only-secret-key-at-least-32-bytes-long",
        "ADMIN_USERNAME": "test-admin",
        "ADMIN_PASSWORD": "test-only-password",
        "SENTRY_DSN": "",
        "BOT_TOKEN": "",
        "ADMIN_IDS": "",
        "ADMIN_ID": "0",
        "BOT_ENABLED": "false",
        "SCHEDULER_ENABLED": "false",
        "COMMUNICATIONS_WORKER_ENABLED": "false",
        "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE": "false",
        "CATALOG_INVALIDATION_WORKER_ENABLED": "false",
        "HA_ALERT_TELEGRAM_BOT_TOKEN": "",
        "HA_ALERT_TELEGRAM_CHAT_ID": "",
        "MAIL_IMAP_USERNAME": "",
        "MAIL_IMAP_PASSWORD": "",
        "MAIL_IMAP_AUTO_IMPORT_ENABLED": "false",
        "MAIL_IMAP_LEAD_AUTO_IMPORT_ENABLED": "false",
        "MAIL_SMTP_USERNAME": "",
        "MAIL_SMTP_PASSWORD": "",
        "DEEPSEEK_TOKEN": "",
        "GOOGLE_VISION_CREDENTIALS_FILE": "",
        "GOOGLE_VISION_PROJECT_ID": "",
        "GITHUB_TOKEN": "",
        "BACKUP_FOLDER_ID": "",
        "MEDIA_WORKER_TOKEN": "",
        "PRODUCT_MEDIA_STORAGE_PROVIDER": "local",
        "PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER": "local",
        "PRODUCT_MEDIA_S3_BUCKET": "",
        "PRODUCT_MEDIA_S3_ENDPOINT_URL": "",
        "PRODUCT_MEDIA_S3_ACCESS_KEY_ID": "",
        "PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY": "",
        "MEDIA_STORAGE_PROVIDER": "local",
        "MEDIA_S3_BUCKET": "",
        "MEDIA_S3_ENDPOINT_URL": "",
        "MEDIA_S3_ACCESS_KEY_ID": "",
        "MEDIA_S3_SECRET_ACCESS_KEY": "",
    }
)
for cloudflare_name in (
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_BASE_URL",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_API_TOKEN_LB_AUDIT",
    "CLOUDFLARE_API_TOKEN_PAGES",
    "CLOUDFLARE_LB",
    "CLOUDFLARE_LB_CONFIG_REQUIRED",
    "CLOUDFLARE_LB_READ_TOKEN",
    "CLOUDFLARE_LB_WRITE_TOKEN",
    "CLOUDFLARE_PAGES_BRANCH",
    "CLOUDFLARE_PAGES_PROJECT",
    "CLOUDFLARE_PURGE_BATCH_SIZE",
    "CLOUDFLARE_PURGE_DRY_RUN",
    "CLOUDFLARE_PURGE_ENABLED",
    "CLOUDFLARE_PURGE_FILES_LIMIT",
    "CLOUDFLARE_PURGE_MIN_INTERVAL_SECONDS",
    "CLOUDFLARE_PURGE_TIMEOUT_SECONDS",
    "CLOUDFLARE_PURGE_ZONE_HOSTNAMES",
    "CLOUDFLARE_ZONE_ID",
):
    os.environ.pop(cloudflare_name, None)

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import AddConstraint
from sqlmodel import SQLModel

from postgres_test_support import (
    BASE_DATABASE_URL_ENV,
    build_test_database_target,
    create_test_database,
    drop_test_database,
    resolve_base_test_database_url,
)


def _running_inside_docker() -> bool:
    return os.path.exists("/.dockerenv")


BASE_TEST_DATABASE_URL = resolve_base_test_database_url(
    running_inside_docker=_running_inside_docker()
)
os.environ.setdefault(BASE_DATABASE_URL_ENV, BASE_TEST_DATABASE_URL)
TEST_DATABASE_TARGET = build_test_database_target(BASE_TEST_DATABASE_URL)
TEST_DATABASE_URL = TEST_DATABASE_TARGET.database_url

# Application modules imported during collection must use the exact same
# physical database as pytest fixtures. In CI, DATABASE_URL otherwise points at
# the app service database while TEST_DATABASE_URL points at db_test.
os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["TEST_POSTGRES_DB"] = TEST_DATABASE_TARGET.database_name

# event_loop fixture removed to let pytest-asyncio handle it with scope=session


def _quoted_metadata_tables(connection) -> str:
    preparer = connection.dialect.identifier_preparer
    return ", ".join(
        preparer.format_table(table) for table in SQLModel.metadata.sorted_tables
    )


async def _seed_system_scope(connection) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO tenant (
                id, slug, display_name, kind, status, is_system, created_at, updated_at
            ) VALUES (
                1, 'mvn', 'Мастер Воздуха', 'operator', 'active', true,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    await connection.execute(
        text(
            """
            INSERT INTO legacy_owner_auth_state (
                id, mode, legacy_token_version, owner_staff_user_id,
                created_at, updated_at
            ) VALUES (
                1, 'legacy', 1, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    await connection.execute(
        text(
            """
            INSERT INTO storefront (
                id, tenant_id, slug, display_name, status, city,
                default_locale, currency, is_default, created_at, updated_at
            ) VALUES (
                1, 1, 'main', 'MVN', 'active', 'Витебск',
                'ru-BY', 'BYN', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    for table_name in ("tenant", "storefront"):
        await connection.execute(
            text(
                "SELECT setval("
                "pg_get_serial_sequence(:table_name, 'id'), "
                f"(SELECT MAX(id) FROM {table_name}), true)"
            ),
            {"table_name": table_name},
        )


async def _apply_expand_phase_schema(connection) -> None:
    # Historical backfill tests exercise the retired nullable schema.
    for table_name, constraint_name in (
        ("lead", "fk_lead_converted_order_scope"),
        ("lead", "fk_lead_storefront_tenant"),
        ("order", "fk_order_customer_tenant"),
        ("order", "fk_order_storefront_tenant"),
        (
            "customer_requisites_recognition",
            "fk_customer_requisites_confirmed_customer_tenant",
        ),
        (
            "customer_requisites_recognition",
            "fk_customer_requisites_duplicate_customer_tenant",
        ),
    ):
        await connection.execute(
            text(
                f'ALTER TABLE "{table_name}" '
                f'DROP CONSTRAINT "{constraint_name}"'
            )
        )
    for table_name, column_names in (
        ("customer", ("tenant_id",)),
        ("customer_requisites_recognition", ("tenant_id",)),
        ("lead", ("tenant_id", "storefront_id")),
        ("order", ("tenant_id", "storefront_id")),
    ):
        for column_name in column_names:
            await connection.execute(
                text(
                    f'ALTER TABLE "{table_name}" '
                    f'ALTER COLUMN "{column_name}" DROP NOT NULL'
                )
            )


async def _truncate_rows(connection) -> None:
    table_list = _quoted_metadata_tables(connection)
    if table_list:
        await connection.execute(
            text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")
        )


async def _reset_rows(engine) -> None:
    async with engine.begin() as connection:
        await _truncate_rows(connection)
        await _seed_system_scope(connection)


async def _prepare_expand_phase_schema(engine) -> None:
    async with engine.begin() as connection:
        await _truncate_rows(connection)
        await _apply_expand_phase_schema(connection)
        await _seed_system_scope(connection)


async def _restore_contracted_schema(engine) -> None:
    async with engine.begin() as connection:
        await _truncate_rows(connection)
        for table_name, column_names in (
            ("customer", ("tenant_id",)),
            ("customer_requisites_recognition", ("tenant_id",)),
            ("lead", ("tenant_id", "storefront_id")),
            ("order", ("tenant_id", "storefront_id")),
        ):
            for column_name in column_names:
                await connection.execute(
                    text(
                        f'ALTER TABLE "{table_name}" '
                        f'ALTER COLUMN "{column_name}" SET NOT NULL'
                    )
                )

        constraint_names = {
            "fk_lead_converted_order_scope",
            "fk_lead_storefront_tenant",
            "fk_order_customer_tenant",
            "fk_order_storefront_tenant",
            "fk_customer_requisites_confirmed_customer_tenant",
            "fk_customer_requisites_duplicate_customer_tenant",
        }
        constraints = {
            constraint.name: constraint
            for table in SQLModel.metadata.sorted_tables
            for constraint in table.constraints
            if constraint.name in constraint_names
        }
        missing_constraints = constraint_names - constraints.keys()
        if missing_constraints:
            raise RuntimeError(
                "Missing contracted test constraints: "
                + ", ".join(sorted(missing_constraints))
            )
        for constraint_name in sorted(constraint_names):
            await connection.execute(AddConstraint(constraints[constraint_name]))
        await _seed_system_scope(connection)


@pytest.fixture(scope="session")
def test_database_url():
    create_test_database(TEST_DATABASE_TARGET)
    try:
        yield TEST_DATABASE_URL
    finally:
        drop_test_database(TEST_DATABASE_TARGET)


@pytest.fixture(scope="session")
async def _session_db_engine(test_database_url):
    # A narrow pytest selection may not import any model-bearing test module.
    # Register the complete metadata explicitly before creating the worker DB.
    import models  # noqa: F401

    # NullPool prevents asyncpg connections created by a session-scoped engine
    # from leaking across pytest-asyncio event loops.
    engine = create_async_engine(test_database_url, echo=False, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="function")
async def db_engine(request, _session_db_engine):
    expand_phase = request.node.get_closest_marker("expand_phase_schema") is not None
    if expand_phase:
        await _prepare_expand_phase_schema(_session_db_engine)
    else:
        await _reset_rows(_session_db_engine)
    try:
        yield _session_db_engine
    finally:
        if expand_phase:
            # Restore the contracted schema even when a historical backfill
            # assertion fails, so the next test cannot inherit nullable scope.
            await _restore_contracted_schema(_session_db_engine)


@pytest.fixture(scope="function")
async def db(db_engine):
    """
    Yields a fresh session for each test.
    The session is rolled back after the test.
    """
    # Connect to the database
    connection = await db_engine.connect()
    # Begin a non-ORM transaction
    transaction = await connection.begin()

    # Bind an individual Session to the connection
    session_factory = sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async with session_factory() as session:
        yield session

    # Rollback the setup transaction
    if transaction.is_active:
        await transaction.rollback()
    await connection.close()


@pytest.fixture
def tenant_scope():
    from services.tenant_scope_service import TenantScope

    return TenantScope(
        tenant_id=1,
        storefront_id=1,
        is_system=True,
        is_canonical_storefront=True,
    )


@pytest.fixture(scope="function")
async def async_client(db):
    from httpx import AsyncClient, ASGITransport
    from main import app
    from core.database import get_session

    async def override_get_session():
        yield db

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
