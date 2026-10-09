"""A private pilot never inherits access from company ownership or system roles."""

from core.config import settings


def has_call_recording_pilot_access(staff_user_id: int | None) -> bool:
    return staff_user_id is not None and staff_user_id in settings.CALL_RECORDINGS_PILOT_STAFF_IDS
