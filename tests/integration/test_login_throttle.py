import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import select

from models import AuthLoginThrottle, StaffUser, TenantMembership
from services.credential_service import CredentialService
from services.login_throttle_service import LoginThrottleService
from services.staff_user_service import StaffUserService


PASSWORD = "safe-pass9"


async def _create_staff(db, *, username: str = "limited-manager") -> StaffUser:
    user = StaffUser(
        display_name="Limited Manager",
        status="active",
        primary_role="manager",
        roles=["manager"],
        username=username,
        password_hash=StaffUserService.hash_password(PASSWORD),
    )
    db.add(user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(user.id),
            role="manager",
            status="active",
        )
    )
    await db.commit()
    return user


async def _failed_login(client: AsyncClient, username: str):
    return await client.post(
        "/login/access-token",
        data={"username": username, "password": "incorrect-password"},
    )


@pytest.mark.asyncio
async def test_password_login_blocks_after_five_failures_and_expires(
    async_client: AsyncClient,
    db,
) -> None:
    user = await _create_staff(db)
    original_hash = str(user.password_hash)
    original_auth_version = int(user.auth_version)

    for _ in range(4):
        response = await _failed_login(async_client, "limited-manager")
        assert response.status_code == 400
        assert response.json()["detail"] == "Incorrect username or password"

    blocked = await _failed_login(async_client, "limited-manager")
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "login_rate_limited"
    assert 1 <= int(blocked.headers["Retry-After"]) <= 900

    correct_while_blocked = await async_client.post(
        "/login/access-token",
        data={"username": "limited-manager", "password": PASSWORD},
    )
    assert correct_while_blocked.status_code == 429
    assert "access_token" not in correct_while_blocked.cookies

    row = await db.get(
        AuthLoginThrottle,
        LoginThrottleService.fingerprint("limited-manager"),
    )
    assert row is not None
    assert row.failure_count == 5
    assert row.fingerprint != "limited-manager"
    database_now = await LoginThrottleService._current_time(db, None)
    row.blocked_until = database_now - timedelta(seconds=1)
    row.window_started_at = database_now - timedelta(minutes=16)
    db.add(row)
    await db.commit()

    global_row = await db.get(
        AuthLoginThrottle,
        LoginThrottleService.global_fingerprint(),
    )
    assert global_row is not None
    assert global_row.blocked_until is None

    recovered = await async_client.post(
        "/login/access-token",
        data={"username": "limited-manager", "password": PASSWORD},
    )
    assert recovered.status_code == 200
    assert "access_token" in recovered.cookies

    await db.refresh(user)
    assert user.password_hash == original_hash
    assert user.auth_version == original_auth_version
    assert await db.get(AuthLoginThrottle, row.fingerprint) is None


@pytest.mark.asyncio
async def test_success_clears_partial_failures_without_touching_other_accounts(
    async_client: AsyncClient,
    db,
) -> None:
    await _create_staff(db, username="manager-a")
    await _create_staff(db, username="manager-b")

    for _ in range(4):
        assert (await _failed_login(async_client, "manager-a")).status_code == 400
    assert (await _failed_login(async_client, "manager-b")).status_code == 400

    success = await async_client.post(
        "/login/access-token",
        data={"username": "manager-a", "password": PASSWORD},
    )
    assert success.status_code == 200

    fingerprints = set(
        (
            await db.execute(select(AuthLoginThrottle.fingerprint))
        ).scalars()
    )
    assert LoginThrottleService.fingerprint("manager-a") not in fingerprints
    assert LoginThrottleService.fingerprint("manager-b") in fingerprints

    for _ in range(4):
        assert (await _failed_login(async_client, "manager-a")).status_code == 400


@pytest.mark.asyncio
async def test_unknown_account_failures_are_atomic_and_use_generic_responses(
    async_client: AsyncClient,
    db,
) -> None:
    responses = [
        await _failed_login(async_client, "unknown-manager")
        for _ in range(5)
    ]

    assert sorted(response.status_code for response in responses) == [400, 400, 400, 400, 429]
    for response in responses:
        if response.status_code == 400:
            assert response.json()["detail"] == "Incorrect username or password"
        else:
            assert response.json()["detail"]["code"] == "login_rate_limited"

    row = await db.get(
        AuthLoginThrottle,
        LoginThrottleService.fingerprint("unknown-manager"),
    )
    assert row is not None
    assert row.failure_count == 5
    assert row.blocked_until is not None


@pytest.mark.asyncio
async def test_concurrent_failures_are_atomic_across_database_sessions(
    test_database_url: str,
    db,
) -> None:
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def record_failure():
        async with session_factory() as session:
            return await LoginThrottleService.record_failure(
                session,
                "concurrent-manager",
            )

    try:
        decisions = await asyncio.gather(
            *[record_failure() for _ in range(5)]
        )
    finally:
        await engine.dispose()

    assert sorted(decision.blocked for decision in decisions) == [
        False,
        False,
        False,
        False,
        True,
    ]
    row = await db.get(
        AuthLoginThrottle,
        LoginThrottleService.fingerprint("concurrent-manager"),
    )
    assert row is not None
    assert row.failure_count == 5
    assert row.blocked_until is not None


@pytest.mark.asyncio
async def test_global_limit_bounds_rows_from_rotating_unknown_usernames(
    async_client: AsyncClient,
    db,
    monkeypatch,
) -> None:
    monkeypatch.setattr(LoginThrottleService, "GLOBAL_MAX_FAILURES", 3)
    await _create_staff(db, username="valid-during-spray")

    decisions = [
        await LoginThrottleService.record_failure(
            db,
            f"rotating-unknown-{index}",
            "127.0.0.1",
        )
        for index in range(6)
    ]

    staff_failure = await _failed_login(async_client, "valid-during-spray")
    staff_success = await async_client.post(
        "/login/access-token",
        data={"username": "valid-during-spray", "password": PASSWORD},
    )
    legacy_success = await async_client.post(
        "/login/access-token",
        data={"username": "test-admin", "password": "test-only-password"},
    )
    unknown_failure = await _failed_login(async_client, "another-unknown")

    fingerprints = set(
        (await db.execute(select(AuthLoginThrottle.fingerprint))).scalars()
    )
    assert len(fingerprints) == 5
    assert LoginThrottleService.global_fingerprint() in fingerprints
    assert decisions[0].blocked is False
    assert decisions[1].blocked is False
    assert all(decision.blocked for decision in decisions[2:])
    assert staff_failure.status_code == 429
    assert staff_success.status_code == 200
    assert legacy_success.status_code == 200
    assert unknown_failure.status_code == 429


@pytest.mark.asyncio
async def test_global_limit_bounds_concurrent_rotating_username_rows(
    test_database_url: str,
    db,
    monkeypatch,
) -> None:
    monkeypatch.setattr(LoginThrottleService, "GLOBAL_MAX_FAILURES", 3)
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def record_failure(index: int):
        async with session_factory() as session:
            return await LoginThrottleService.record_failure(
                session,
                f"concurrent-rotating-{index}",
            )

    try:
        decisions = await asyncio.gather(
            *[record_failure(index) for index in range(12)]
        )
    finally:
        await engine.dispose()

    fingerprints = set(
        (await db.execute(select(AuthLoginThrottle.fingerprint))).scalars()
    )
    assert len(fingerprints) == 5
    assert LoginThrottleService.global_fingerprint() in fingerprints
    assert sum(decision.blocked for decision in decisions) == 10


@pytest.mark.asyncio
async def test_expired_throttle_rows_are_removed_on_next_failure(db) -> None:
    stale_fingerprint = LoginThrottleService.fingerprint("stale-manager")
    stale_time = datetime.now(timezone.utc) - timedelta(hours=1)
    db.add(
        AuthLoginThrottle(
            fingerprint=stale_fingerprint,
            failure_count=1,
            window_started_at=stale_time,
            updated_at=stale_time,
        )
    )
    await db.commit()

    await LoginThrottleService.record_failure(db, "fresh-manager")

    assert await db.get(AuthLoginThrottle, stale_fingerprint) is None


@pytest.mark.asyncio
async def test_source_limit_stops_bcrypt_and_writes_without_blocking_other_source(
    async_client: AsyncClient,
    db,
    monkeypatch,
) -> None:
    monkeypatch.setattr(LoginThrottleService, "SOURCE_MAX_FAILURES", 3)
    original_verify = CredentialService.verify_password.__func__
    checked_hashes: list[str | None] = []

    def recording_verify(cls, password, password_hash):
        checked_hashes.append(password_hash)
        return original_verify(cls, password, password_hash)

    monkeypatch.setattr(
        CredentialService,
        "verify_password",
        classmethod(recording_verify),
    )
    blocked_source_headers = {"X-Forwarded-For": "198.51.100.10"}

    responses = [
        await async_client.post(
            "/login/access-token",
            data={
                "username": f"source-spray-{index}",
                "password": "incorrect-password",
            },
            headers=blocked_source_headers,
        )
        for index in range(3)
    ]
    assert [response.status_code for response in responses] == [400, 400, 429]
    assert len(checked_hashes) == 3
    fingerprints_before = set(
        (await db.execute(select(AuthLoginThrottle.fingerprint))).scalars()
    )

    rejected_before_bcrypt = await async_client.post(
        "/login/access-token",
        data={"username": "source-spray-next", "password": "incorrect-password"},
        headers=blocked_source_headers,
    )
    fingerprints_after = set(
        (await db.execute(select(AuthLoginThrottle.fingerprint))).scalars()
    )

    assert rejected_before_bcrypt.status_code == 429
    assert len(checked_hashes) == 3
    assert fingerprints_after == fingerprints_before

    await _create_staff(db, username="other-source-manager")
    other_source_success = await async_client.post(
        "/login/access-token",
        data={"username": "other-source-manager", "password": PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.11"},
    )

    assert other_source_success.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_correct_guess_cannot_bypass_fifth_failure_reservation(
    test_database_url: str,
    db,
    monkeypatch,
) -> None:
    from core.database import get_session
    from main import app

    engine = create_async_engine(test_database_url, poolclass=NullPool)
    session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as setup_session:
        await _create_staff(setup_session, username="reservation-manager")

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    source_headers = {"X-Forwarded-For": "198.51.100.77"}

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(4):
                response = await client.post(
                    "/login/access-token",
                    data={
                        "username": "reservation-manager",
                        "password": "incorrect-password",
                    },
                    headers=source_headers,
                )
                assert response.status_code == 400

            verifier_entered = asyncio.Event()
            release_verifier = asyncio.Event()
            verified_passwords: list[str] = []

            async def held_verifier(cls, password, password_hash):
                verified_passwords.append(password)
                verifier_entered.set()
                await release_verifier.wait()
                return False

            monkeypatch.setattr(
                CredentialService,
                "verify_password_async",
                classmethod(held_verifier),
            )

            fifth_failure_task = asyncio.create_task(
                client.post(
                    "/login/access-token",
                    data={
                        "username": "reservation-manager",
                        "password": "incorrect-password",
                    },
                    headers=source_headers,
                )
            )
            await asyncio.wait_for(verifier_entered.wait(), timeout=5)

            correct_guess_task = asyncio.create_task(
                client.post(
                    "/login/access-token",
                    data={"username": "reservation-manager", "password": PASSWORD},
                    headers=source_headers,
                )
            )
            await asyncio.sleep(0.2)

            assert verified_passwords == ["incorrect-password"]
            assert not correct_guess_task.done()

            release_verifier.set()
            fifth_failure, correct_guess = await asyncio.gather(
                fifth_failure_task,
                correct_guess_task,
            )

            assert fifth_failure.status_code == 429
            assert correct_guess.status_code == 429
            assert verified_passwords == ["incorrect-password"]
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
