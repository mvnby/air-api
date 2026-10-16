"""Notification-only alias resolution. Never use this for authentication."""

from sqlmodel import select

from models import StaffUser
from models.staff_telegram import StaffTelegramRetiredIdentity
from datetime import datetime, timezone


async def retire_telegram_identity(session, telegram_id, staff_user_id):
    if telegram_id is None:
        return
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    await session.execute(insert(StaffTelegramRetiredIdentity).values(
        telegram_id=int(telegram_id), staff_user_id=int(staff_user_id), retired_at=datetime.now(timezone.utc),
    ).on_conflict_do_nothing(index_elements=["telegram_id"]))


async def legacy_telegram_allowed(session, telegram_id):
    return await session.get(StaffTelegramRetiredIdentity, int(telegram_id)) is None


def notifications_enabled(user) -> bool:
    return (getattr(user, "telegram_notifications_enabled", True) is not False
            and not getattr(user, "merged_into_staff_user_id", None))


async def notification_identity(session, staff_user_id):
    user = (await session.execute(select(StaffUser).where(
        StaffUser.id == staff_user_id,
    ).execution_options(populate_existing=True))).scalar_one_or_none()
    # A single reviewed historical alias is enough; reject malformed chains.
    if user is not None and user.merged_into_staff_user_id:
        user = (await session.execute(select(StaffUser).where(
            StaffUser.id == user.merged_into_staff_user_id,
        ).execution_options(populate_existing=True))).scalar_one_or_none()
    if user is None or user.status != "active" or not notifications_enabled(user):
        return None
    return user


async def legacy_recipient_ids(session, candidate_ids):
    candidates = [int(value) for value in candidate_ids]
    if not candidates:
        return []
    # Existing identities remain authoritative even when opted out/disabled;
    # legacy ADMIN_IDS must never resurrect their delivery.
    known = set((await session.execute(select(StaffUser.telegram_id).where(
        StaffUser.telegram_id.in_(candidates),
    ))).scalars())
    retired = set((await session.execute(select(StaffTelegramRetiredIdentity.telegram_id).where(
        StaffTelegramRetiredIdentity.telegram_id.in_(candidates),
    ))).scalars())
    return [value for value in candidates if value not in known and value not in retired]
