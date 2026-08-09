from sqlalchemy.engine import make_url

from postgres_test_support import (
    POSTGRES_IDENTIFIER_LIMIT,
    build_test_database_target,
    resolve_base_test_database_url,
)


BASE_URL = (
    "postgresql+asyncpg://postgres:postgres@localhost:5433/"
    "air_conditioners_test"
)


def test_worker_database_names_are_distinct_and_keep_the_test_marker():
    first = build_test_database_target(
        BASE_URL,
        run_id="same-test-run",
        worker_id="gw0",
    )
    second = build_test_database_target(
        BASE_URL,
        run_id="same-test-run",
        worker_id="gw1",
    )

    assert first.database_name != second.database_name
    assert first.database_name.endswith("_gw0")
    assert second.database_name.endswith("_gw1")
    assert "test" in first.database_name
    assert make_url(first.database_url).database == first.database_name


def test_worker_database_name_is_sanitized_and_within_postgres_limit():
    target = build_test_database_target(
        BASE_URL.replace("air_conditioners_test", "very_long_test_" + "x" * 80),
        run_id="run with unsafe / separators",
        worker_id="GW 17/unsafe",
    )

    assert len(target.database_name) <= POSTGRES_IDENTIFIER_LIMIT
    assert target.database_name.endswith("_gw_17_unsafe")
    assert "/" not in target.database_name
    assert " " not in target.database_name


def test_non_test_database_is_never_accepted_even_when_password_contains_test():
    unsafe_url = (
        "postgresql+asyncpg://postgres:test-password@localhost:5432/air_conditioners"
    )

    try:
        build_test_database_target(unsafe_url, run_id="run", worker_id="master")
    except ValueError as exc:
        assert "non-test database" in str(exc)
    else:
        raise AssertionError("A production-shaped database URL was accepted")


def test_database_name_requires_a_test_token_not_a_substring():
    unsafe_url = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/contest_production"
    )

    try:
        build_test_database_target(unsafe_url, run_id="run", worker_id="master")
    except ValueError as exc:
        assert "non-test database" in str(exc)
    else:
        raise AssertionError("A database without an explicit test token was accepted")


def test_base_url_resolution_ignores_non_test_database(monkeypatch):
    monkeypatch.delenv("PYTEST_BASE_DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:test-password@localhost:5432/air_conditioners",
    )
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "postgres")
    monkeypatch.setenv("TEST_POSTGRES_DB", "air_conditioners_test")

    resolved = resolve_base_test_database_url(running_inside_docker=False)

    assert make_url(resolved).database == "air_conditioners_test"
    assert make_url(resolved).port == 5433


def test_explicit_base_database_override_fails_closed(monkeypatch):
    monkeypatch.setenv(
        "PYTEST_BASE_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/air_conditioners",
    )

    try:
        resolve_base_test_database_url(running_inside_docker=False)
    except ValueError as exc:
        assert "PYTEST_BASE_DATABASE_URL" in str(exc)
    else:
        raise AssertionError("An unsafe explicit base database was ignored")


def test_fallback_url_encodes_password_characters(monkeypatch):
    monkeypatch.delenv("PYTEST_BASE_DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss/word")
    monkeypatch.setenv("TEST_POSTGRES_DB", "air_conditioners_test")

    resolved = resolve_base_test_database_url(running_inside_docker=False)

    assert make_url(resolved).password == "p@ss/word"
