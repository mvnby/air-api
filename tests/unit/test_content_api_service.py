from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.content_api_service import ContentApiService


def test_sanitize_service_description_removes_scripts_and_handlers():
    raw = '<p onclick="alert(1)">Hello<script>alert(1)</script><strong>World</strong></p>'
    sanitized = ContentApiService._sanitize_service_description(raw)

    assert sanitized is not None
    assert "<script" not in sanitized
    assert "onclick" not in sanitized
    assert "<strong>World</strong>" in sanitized


def test_sanitize_service_description_rejects_dangerous_anchor_href():
    raw = '<p><a href="javascript:alert(1)" target="_blank">Click</a></p>'
    sanitized = ContentApiService._sanitize_service_description(raw)

    assert sanitized is not None
    assert "javascript:" not in sanitized.lower()
    assert 'href=' not in sanitized
    assert 'rel="noopener noreferrer"' in sanitized


def test_sanitize_service_description_unwraps_disallowed_tags():
    raw = "<div>Before<section><em>Safe</em></section>After</div>"
    sanitized = ContentApiService._sanitize_service_description(raw)

    assert sanitized is not None
    assert "<div" not in sanitized
    assert "<section" not in sanitized
    assert "<em>Safe</em>" in sanitized
    assert "Before" in sanitized and "After" in sanitized


@pytest.mark.asyncio
async def test_public_config_returns_only_storefront_allowlist():
    result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(
            all=lambda: [
                SimpleNamespace(key="phone", value="+375 29 000-00-00"),
                SimpleNamespace(key="install_discount", value="100"),
                SimpleNamespace(key="supplier_default_spreadsheet_id", value="private-sheet"),
                SimpleNamespace(key="catalog_static_rebuild_last_error", value="internal-error"),
            ]
        )
    )
    session = SimpleNamespace(execute=AsyncMock(return_value=result))

    payload = await ContentApiService.get_global_config_map(session)

    assert payload == {
        "phone": "+375 29 000-00-00",
        "install_discount": "100",
    }
