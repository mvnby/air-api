"""Server-owned read-only policy for demonstration tenants."""

from fastapi import HTTPException, Request

from routers.manager_operation_ids import (
    CALCULATE_MANAGER_INSTALL_ESTIMATE,
    GET_MANAGER_DOCUMENT_DRIVE_AUTHORIZATION_URL,
    GET_MANAGER_GOOGLE_AUTH_URL,
    GET_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION,
    GET_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
)


DEMO_READ_ONLY_MESSAGE = "Демонстрационный режим: изменения не сохраняются"
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_READ_ONLY_POST_OPERATIONS = frozenset({
    CALCULATE_MANAGER_INSTALL_ESTIMATE,
    "calculate_public_service_tariff",
    "resolve_public_installation_tariff",
    "preview_public_installation_estimate",
})
_CONNECTION_OPERATIONS = frozenset({
    GET_MANAGER_DOCUMENT_DRIVE_AUTHORIZATION_URL,
    GET_MANAGER_GOOGLE_AUTH_URL,
    GET_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION,
    GET_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
})


def enforce_demo_read_only(request: Request, *, demo_read_only: bool) -> None:
    if not demo_read_only:
        return
    route = request.scope.get("route")
    operation_id = getattr(route, "operation_id", None)
    if operation_id not in _CONNECTION_OPERATIONS:
        if request.method in _READ_METHODS:
            return
        if request.method == "POST" and operation_id in _READ_ONLY_POST_OPERATIONS:
            return
    raise HTTPException(
        status_code=403,
        detail={"code": "demo_read_only", "message": DEMO_READ_ONLY_MESSAGE},
    )
