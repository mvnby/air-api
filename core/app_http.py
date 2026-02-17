from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from core.app_constants import (
    ADMIN_ROUTE_PREFIX,
    INTERNAL_SERVER_ERROR_MESSAGE,
    INTERNAL_SERVER_ERROR_TITLE,
)
from core.config import settings
from core.logger import logger


def _is_admin_path(path: str) -> bool:
    return path.startswith(ADMIN_ROUTE_PREFIX)


def _admin_error_response(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": INTERNAL_SERVER_ERROR_TITLE, "detail": detail},
    )


def _public_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"message": INTERNAL_SERVER_ERROR_MESSAGE},
    )


async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception at {request.url}: {exc}")

    if _is_admin_path(str(request.url.path)):
        return _admin_error_response(str(exc))

    return _public_error_response()


def configure_http(app: FastAPI) -> None:
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
