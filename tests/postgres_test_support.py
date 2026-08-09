from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url


POSTGRES_IDENTIFIER_LIMIT = 63
BASE_DATABASE_URL_ENV = "PYTEST_BASE_DATABASE_URL"
RUN_ID_ENV = "PYTEST_DB_RUN_ID"


@dataclass(frozen=True)
class TestDatabaseTarget:
    base_database_name: str
    database_name: str
    database_url: str
    run_id: str
    worker_id: str


def _render_url(url) -> str:
    return url.render_as_string(hide_password=False)


def _has_test_marker(database_name: str) -> bool:
    return re.search(r"(?:^|_)test(?:_|$)", database_name.lower()) is not None


def _test_database_url_from_environment() -> str | None:
    base_override = os.environ.get(BASE_DATABASE_URL_ENV)
    if base_override:
        parsed = make_url(base_override)
        database_name = parsed.database or ""
        if parsed.get_backend_name() != "postgresql" or not _has_test_marker(
            database_name
        ):
            raise ValueError(
                f"{BASE_DATABASE_URL_ENV} must name a PostgreSQL test database"
            )
        return _render_url(parsed)

    for variable_name in ("TEST_DATABASE_URL", "DATABASE_URL"):
        configured_url = os.environ.get(variable_name)
        if not configured_url:
            continue
        parsed = make_url(configured_url)
        database_name = parsed.database or ""
        if parsed.get_backend_name() == "postgresql" and _has_test_marker(
            database_name
        ):
            return _render_url(parsed)
    return None


def resolve_base_test_database_url(*, running_inside_docker: bool) -> str:
    configured_url = _test_database_url_from_environment()
    if configured_url:
        return configured_url

    pg_user = os.environ.get("POSTGRES_USER", "mvnadmin")
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "securepass")
    test_db_host = os.environ.get("TEST_DB_HOST")
    if not test_db_host:
        test_db_host = "db_test" if running_inside_docker else "localhost"
    test_db_port = os.environ.get("TEST_DB_PORT") or os.environ.get("POSTGRES_PORT")
    if not test_db_port:
        test_db_port = "5432" if test_db_host == "db_test" else "5433"
    test_db_name = os.environ.get("TEST_POSTGRES_DB", "air_conditioners_test")
    return _render_url(
        URL.create(
            "postgresql+asyncpg",
            username=pg_user,
            password=pg_pass,
            host=test_db_host,
            port=int(test_db_port),
            database=test_db_name,
        )
    )


def _safe_identity_part(value: str, *, fallback: str) -> str:
    sanitized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return sanitized or fallback


def build_test_database_target(
    base_database_url: str,
    *,
    run_id: str | None = None,
    worker_id: str | None = None,
) -> TestDatabaseTarget:
    parsed = make_url(base_database_url)
    base_database_name = parsed.database or ""
    if parsed.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL is required for the test database")
    if not _has_test_marker(base_database_name):
        raise ValueError(
            "Refusing to derive a pytest database from a non-test database"
        )

    selected_run_id = (
        run_id
        or os.environ.get("PYTEST_XDIST_TESTRUNUID")
        or os.environ.get(RUN_ID_ENV)
        or uuid.uuid4().hex
    )
    selected_worker_id = (
        worker_id or os.environ.get("PYTEST_XDIST_WORKER") or "master"
    )
    worker_token = _safe_identity_part(selected_worker_id, fallback="master")[:12]
    run_token = hashlib.sha256(selected_run_id.encode("utf-8")).hexdigest()[:10]
    suffix = f"_{run_token}_{worker_token}"
    available_base_length = POSTGRES_IDENTIFIER_LIMIT - len(suffix)
    database_name = f"{base_database_name[:available_base_length]}{suffix}"
    database_url = _render_url(parsed.set(database=database_name))
    return TestDatabaseTarget(
        base_database_name=base_database_name,
        database_name=database_name,
        database_url=database_url,
        run_id=selected_run_id,
        worker_id=selected_worker_id,
    )


def _admin_connection_kwargs(database_url: str) -> dict[str, object]:
    parsed = make_url(database_url)
    kwargs: dict[str, object] = {
        "dbname": "postgres",
        "connect_timeout": 10,
        "autocommit": True,
    }
    for key, value in (
        ("user", parsed.username),
        ("password", parsed.password),
        ("host", parsed.host),
        ("port", parsed.port),
    ):
        if value is not None:
            kwargs[key] = value
    return kwargs


def _assert_safe_target(target: TestDatabaseTarget) -> None:
    if target.database_name == target.base_database_name:
        raise ValueError("The isolated database must differ from the base database")
    if not _has_test_marker(target.database_name):
        raise ValueError("Refusing to manage a database without a test marker")
    if len(target.database_name) > POSTGRES_IDENTIFIER_LIMIT:
        raise ValueError("The isolated database name exceeds the PostgreSQL limit")


def drop_test_database(target: TestDatabaseTarget) -> None:
    _assert_safe_target(target)
    with psycopg.connect(**_admin_connection_kwargs(target.database_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s
                  AND pid <> pg_backend_pid()
                """,
                (target.database_name,),
            )
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(target.database_name)
                )
            )


def create_test_database(target: TestDatabaseTarget) -> None:
    _assert_safe_target(target)
    drop_test_database(target)
    with psycopg.connect(**_admin_connection_kwargs(target.database_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(target.database_name)
                )
            )
