from core.app_observability import _scrub_sentry_event, init_sentry


def test_sentry_uses_configured_sampling_and_does_not_capture_request_bodies(monkeypatch):
    captured = {}

    monkeypatch.setattr("core.app_observability.settings.SENTRY_DSN", "https://public@example.test/1")
    monkeypatch.setattr("core.app_observability.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("core.app_observability.settings.SENTRY_TRACES_SAMPLE_RATE", 0.2)
    monkeypatch.setattr("core.app_observability.settings.SENTRY_PROFILES_SAMPLE_RATE", 0.0)
    monkeypatch.setattr("core.app_observability.sentry_sdk.init", lambda **kwargs: captured.update(kwargs))

    init_sentry()

    assert captured["traces_sample_rate"] == 0.2
    assert captured["profiles_sample_rate"] == 0.0
    assert captured["send_default_pii"] is False
    assert captured["max_request_body_size"] == "never"
    assert captured["include_local_variables"] is False
    assert captured["before_send"] is _scrub_sentry_event
    assert captured["before_send_transaction"] is _scrub_sentry_event


def test_sentry_scrubber_removes_request_secrets_and_exception_messages():
    event = {
        "request": {
            "url": "https://mvn.by/api/v1/orders",
            "query_string": "phone=secret",
            "headers": {"authorization": "Bearer secret"},
            "data": {"phone": "secret"},
            "cookies": {"session": "secret"},
        },
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": "oauth-code-secret",
                    "stacktrace": {"frames": [{"vars": {"token": "secret"}}]},
                }
            ]
        },
    }

    scrubbed = _scrub_sentry_event(event, {})

    assert scrubbed["request"] == {"url": "https://mvn.by/api/v1/orders"}
    assert scrubbed["exception"]["values"][0]["value"] == "RuntimeError message redacted"
    assert "vars" not in scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]


def test_sentry_scrubber_removes_transaction_query_string_and_span_secrets(monkeypatch):
    monkeypatch.setattr(
        "core.app_observability.settings.BOT_TOKEN",
        "123456789:telegram-secret-token",
    )
    event = {
        "type": "transaction",
        "request": {
            "url": "https://mvn.by/api/manager/google-auth/callback",
            "query_string": "code=oauth-secret&state=secret",
        },
        "spans": [
            {
                "description": (
                    "POST https://api.telegram.org/"
                    "bot123456789:telegram-secret-token/sendRichMessage"
                ),
                "data": {
                    "url": (
                        "https://api.telegram.org/"
                        "bot123456789:telegram-secret-token/sendRichMessage"
                    ),
                    "http.query": "chat_id=secret",
                },
            }
        ],
    }

    scrubbed = _scrub_sentry_event(event, {})

    assert scrubbed["request"] == {
        "url": "https://mvn.by/api/manager/google-auth/callback"
    }
    rendered = repr(scrubbed["spans"])
    assert "telegram-secret-token" not in rendered
    assert "http.query" not in rendered
    assert "[redacted]" in rendered


def test_sentry_scrubber_strips_query_and_fragment_from_urls_in_nested_strings():
    event = {
        "type": "transaction",
        "spans": [
            {
                "description": (
                    "GET https://suggest-maps.yandex.ru/v1/suggest"
                    "?apikey=yandex-secret&text=private%20address"
                ),
                "data": {
                    "url": (
                        "https://suggest-maps.yandex.ru/v1/suggest"
                        "?apikey=yandex-secret&text=private%20address#result"
                    )
                },
            }
        ],
    }

    scrubbed = _scrub_sentry_event(event, {})

    rendered = repr(scrubbed["spans"])
    assert "yandex-secret" not in rendered
    assert "private%20address" not in rendered
    assert "?" not in rendered
    assert "#result" not in rendered
    assert "https://suggest-maps.yandex.ru/v1/suggest" in rendered
