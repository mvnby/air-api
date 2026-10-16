"""Actor-aware boundaries for tenant staff administration."""

from __future__ import annotations


class StaffAccessPolicyError(ValueError):
    def __init__(self, message: str, *, code: str, status_code: int = 403):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class StaffAccessPolicy:
    ORDINARY_ROLES = frozenset({"manager", "catalog_editor", "installer"})

    @classmethod
    def validate_mutation(
        cls,
        *,
        actor_role: str | None,
        is_platform_owner: bool,
        target_role: str | None,
        requested_role: str,
        target_is_platform_owner: bool = False,
    ) -> None:
        # None is reserved for trusted service callers. HTTP routes always pass
        # the authenticated current membership role, including an empty value.
        if actor_role is None:
            return
        if target_is_platform_owner and not is_platform_owner:
            raise StaffAccessPolicyError(
                "Учётную запись владельца платформы может изменять только владелец платформы",
                code="platform_owner_protected",
            )
        if is_platform_owner:
            return
        if actor_role == "owner":
            return
        if (
            actor_role == "admin"
            and target_role in cls.ORDINARY_ROLES | {None}
            and requested_role in cls.ORDINARY_ROLES
        ):
            return
        raise StaffAccessPolicyError(
            "Недостаточно прав для изменения владельца или администратора организации",
            code="staff_role_forbidden",
        )

    @staticmethod
    def require_remaining_owner(active_owner_count: int) -> None:
        if active_owner_count <= 1:
            raise StaffAccessPolicyError(
                "Нельзя отключить или понизить роль последнего активного владельца организации",
                code="last_active_owner",
                status_code=409,
            )

    @staticmethod
    def validate_catalog_grantee_credentials(
        *,
        actor_role: str | None,
        is_platform_owner: bool,
        has_catalog_grant: bool,
        credentials_changed: bool,
    ) -> None:
        if (
            actor_role is not None
            and not is_platform_owner
            and has_catalog_grant
            and credentials_changed
        ):
            raise StaffAccessPolicyError(
                "Данные входа сотрудника с доступом к общему каталогу может изменять только владелец платформы",
                code="catalog_grantee_identity_protected",
            )
