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

import asyncio
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

def _running_inside_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _resolve_test_database_url() -> str:
    configured_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if configured_url and "test" in configured_url.lower():
        return configured_url

    pg_user = os.environ.get("POSTGRES_USER", "mvnadmin")
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "securepass")
    test_db_host = os.environ.get("TEST_DB_HOST")
    if not test_db_host:
        test_db_host = "db_test" if _running_inside_docker() else "localhost"
    test_db_port = os.environ.get("TEST_DB_PORT") or os.environ.get("POSTGRES_PORT")
    if not test_db_port:
        test_db_port = "5432" if test_db_host == "db_test" else "5433"
    test_db_name = os.environ.get("TEST_POSTGRES_DB", "air_conditioners_test")
    return f"postgresql+asyncpg://{pg_user}:{pg_pass}@{test_db_host}:{test_db_port}/{test_db_name}"


# CRITICAL: Always use the TEST database for tests.
TEST_DATABASE_URL = _resolve_test_database_url()

# Safety net: abort if the URL doesn't contain 'test'
assert "test" in TEST_DATABASE_URL.lower(), (
    f"SAFETY: Refusing to run tests against a non-test database! URL={TEST_DATABASE_URL}"
)

# event_loop fixture removed to let pytest-asyncio handle it with scope=session


@pytest.fixture(scope="function")
async def db_engine(request):
    """
    Create a fresh database engine for the test session.
    Always uses the dedicated test database (db_test service).
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Basic check if DB is up
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.execute(
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
        if request.node.get_closest_marker("expand_phase_schema"):
            # Historical backfill tests exercise the retired nullable schema.
            # Production and every other test use the contracted NOT NULL
            # metadata so missing provenance cannot be hidden by fixtures.
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
                await conn.execute(
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
                    await conn.execute(
                        text(
                            f'ALTER TABLE "{table_name}" '
                            f'ALTER COLUMN "{column_name}" DROP NOT NULL'
                        )
                    )
        await conn.execute(
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
    
    yield engine
    
    await engine.dispose()

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
    )
    
    async with session_factory() as session:
        yield session
    
    # Rollback the setup transaction
    await transaction.rollback()
    await connection.close()


@pytest.fixture
def tenant_scope():
    from services.tenant_scope_service import TenantScope

    return TenantScope(tenant_id=1, storefront_id=1, is_system=True)

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
