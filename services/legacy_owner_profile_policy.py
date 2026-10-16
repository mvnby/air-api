"""One owner-profile invariant shared by login, self-service and recovery."""

import json


class LegacyOwnerProfilePolicy:
    @staticmethod
    def allows(user, *, installer=None) -> bool:
        if user is None or getattr(user, "merged_into_staff_user_id", None) is not None:
            return False
        roles = user.roles
        if isinstance(roles, str):
            try:
                roles = json.loads(roles)
            except (ValueError, TypeError):
                return False
        if not isinstance(roles, list):
            return False
        roles = {str(role).strip().lower() for role in roles}
        if user.status != "active" or user.primary_role != "owner":
            return False
        if user.legacy_installer_id is None:
            if roles != {"owner"}:
                return False
        elif (
            roles != {"owner", "installer"}
            or installer is None
            or installer.id != user.legacy_installer_id
            or installer.telegram_id != user.telegram_id
        ):
            return False
        if user.telegram_id is not None and getattr(user, "telegram_verified_at", None) is None:
            return False
        if user.telegram_id is None and user.telegram_username:
            return False
        return True
