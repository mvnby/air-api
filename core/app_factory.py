from fastapi import FastAPI

from core.app_http import configure_http
from core.app_lifespan import app_lifespan
from core.app_manager import setup_manager_spa
from core.app_observability import init_sentry
from core.app_paths import AppPaths, get_app_paths
from core.app_routing import register_app_routers
from core.app_static import mount_static_and_media


def _configure_app_layers(app: FastAPI, paths: AppPaths) -> None:
    configure_http(app)
    register_app_routers(app)
    mount_static_and_media(app, paths.base_dir)
    setup_manager_spa(app, paths.manager_dist)


def create_app() -> FastAPI:
    init_sentry()

    paths = get_app_paths()
    app = FastAPI(
        lifespan=app_lifespan,
        title="Kitlane / MVN HTTP API",
        description=(
            "HTTP operations for the public storefront, authenticated Manager, "
            "internal staff bot and connector OAuth. Each surface has its own access "
            "and data-scope rules; a listed route is not a public partner API. "
            "See the [API guide](https://github.com/mvnby/air-api/blob/main/docs/api/README.md).\n\n"
            "Storefront HMAC headers are checked by middleware and are not represented "
            "as an OpenAPI security scheme; see the "
            "[signed request contract](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md). "
            "The optional /api/connector/mcp ASGI transport is outside this schema; "
            "MCP clients discover tools through tools/list. See the "
            "[connector contract](https://github.com/mvnby/air-api/blob/main/docs/chatgpt-connector.md).\n\n"
            "info.version is the existing schema metadata value, not a business API "
            "compatibility promise. The storefront and bot use v1 URL prefixes; "
            "Manager URLs have no version prefix. Check the deployed release and "
            "the specific consumer contract when assessing compatibility."
        ),
    )
    _configure_app_layers(app, paths)

    return app
