from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from core.app_constants import (
    INTERNAL_SERVER_ERROR_MESSAGE,
)
from core.config import settings
from core.logger import logger
from core.manager_error_codes import INTERNAL_ERROR, VALIDATION_ERROR, resolve_manager_error_message
from core.manager_telemetry import ManagerTelemetryService


def _is_manager_api_path(path: str) -> bool:
    return path.startswith("/api/manager")


def _public_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"message": INTERNAL_SERVER_ERROR_MESSAGE},
    )


def _manager_error_response(*, status_code: int, message: str, error_code: str, field_errors: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": {
                "message": message,
                "error_code": error_code,
                "field_errors": field_errors or {},
            }
        },
    )


def _serialize_validation_errors(errors: list[dict]) -> list[dict]:
    serialized: list[dict] = []
    for item in errors:
        clean_item = dict(item)
        ctx = clean_item.get("ctx")
        if isinstance(ctx, dict):
            clean_ctx = {}
            for key, value in ctx.items():
                clean_ctx[key] = str(value) if isinstance(value, Exception) else value
            clean_item["ctx"] = clean_ctx
        serialized.append(clean_item)
    return serialized


async def manager_validation_exception_handler(request: Request, exc: RequestValidationError):
    if not _is_manager_api_path(str(request.url.path)):
        return JSONResponse(status_code=422, content={"detail": _serialize_validation_errors(exc.errors())})

    field_errors: dict[str, str] = {}
    for item in exc.errors():
        loc = item.get("loc", [])
        if not loc:
            continue
        field = str(loc[-1])
        if field and field not in field_errors:
            field_errors[field] = item.get("msg", "Некорректное значение")

    ManagerTelemetryService.record_error(
        endpoint=str(request.url.path),
        status_code=422,
        error_code=VALIDATION_ERROR,
        field_errors=field_errors,
    )
    return _manager_error_response(
        status_code=422,
        message=resolve_manager_error_message(VALIDATION_ERROR),
        error_code=VALIDATION_ERROR,
        field_errors=field_errors,
    )


async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception at {request.url}: {exc}")

    if _is_manager_api_path(str(request.url.path)):
        ManagerTelemetryService.record_error(
            endpoint=str(request.url.path),
            status_code=500,
            error_code=INTERNAL_ERROR,
        )
        return _manager_error_response(
            status_code=500,
            message=resolve_manager_error_message(INTERNAL_ERROR, INTERNAL_SERVER_ERROR_MESSAGE),
            error_code=INTERNAL_ERROR,
        )

    return _public_error_response()


def configure_http(app: FastAPI) -> None:
    app.exception_handler(RequestValidationError)(manager_validation_exception_handler)
    app.exception_handler(Exception)(global_exception_handler)

    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
