"""Optional, dependency-free MCP Apps view; business tools remain headless."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource


SALES_UI_URI = "ui://kitlane/sales/v1.html"
SALES_UI_MIME = "text/html;profile=mcp-app"
_ASSET = Path(__file__).resolve().parents[1] / "static" / "mcp" / "sales.html"


def _image_origins() -> list[str]:
    # Only public, configured media origins, never arbitrary tool-result URLs.
    from core.config import settings
    from services.connector_auth_policy import issuer

    origins = set()
    for value in (settings.PUBLIC_SITE_URL, issuer(),
                  settings.PRODUCT_MEDIA_S3_PUBLIC_BASE_URL, settings.MEDIA_S3_PUBLIC_BASE_URL):
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.netloc and not parsed.username and not parsed.password:
            origins.add(f"https://{parsed.netloc}")
    return sorted(origins)


def _metadata() -> dict:
    return {"ui": {"prefersBorder": True, "csp": {
        "connectDomains": [], "resourceDomains": _image_origins(), "frameDomains": [],
    }}}


def sales_ui_resource() -> Resource:
    return Resource(uri=SALES_UI_URI, name="Kitlane sales comparison",
                    description="Equipment and installation alternatives, or saved quote readiness.",
                    mimeType=SALES_UI_MIME, _meta=_metadata())


def sales_ui_contents() -> list[ReadResourceContents]:
    origins = json.dumps(_image_origins()).replace("<", "\\u003c")
    html = _ASSET.read_text(encoding="utf-8").replace("/*IMAGE_ORIGINS*/[]", origins)
    return [ReadResourceContents(content=html, mime_type=SALES_UI_MIME, meta=_metadata())]
