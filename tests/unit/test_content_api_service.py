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
