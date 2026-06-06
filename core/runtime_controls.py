from dataclasses import dataclass


ACTIVE_APP_ROLES = frozenset({"primary", "active"})
STANDBY_APP_ROLES = frozenset({"standby", "passive", "readonly", "read-only", "read_only"})


@dataclass(frozen=True)
class RuntimeControlDecision:
    enabled: bool
    reason: str


def normalize_app_role(app_role: str | None) -> str:
    role = (app_role or "primary").strip().lower()
    return role or "primary"


def resolve_single_active_control(
    *,
    app_role: str | None,
    explicit_enabled: bool | None,
    env_var_name: str,
    process_label: str,
) -> RuntimeControlDecision:
    if explicit_enabled is not None:
        state = "true" if explicit_enabled else "false"
        action = "enables" if explicit_enabled else "disables"
        return RuntimeControlDecision(
            enabled=bool(explicit_enabled),
            reason=f"{env_var_name}={state} explicitly {action} {process_label}",
        )

    role = normalize_app_role(app_role)
    if role in ACTIVE_APP_ROLES:
        return RuntimeControlDecision(
            enabled=True,
            reason=f"APP_ROLE={role} allows active {process_label}",
        )
    if role in STANDBY_APP_ROLES:
        return RuntimeControlDecision(
            enabled=False,
            reason=f"APP_ROLE={role} disables active {process_label}",
        )

    return RuntimeControlDecision(
        enabled=False,
        reason=(
            f"APP_ROLE={role!r} is not an active role; "
            f"{process_label} is disabled by default"
        ),
    )
