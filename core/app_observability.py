import logging
import re
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk

from core.config import settings


_TELEGRAM_TOKEN_IN_URL = re.compile(r"(?<=/bot)[0-9]+:[A-Za-z0-9_-]+")
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+")
_PERSONAL_OFFER_TOKEN_IN_PATH = re.compile(r"(/api/v1/personal-offers/|/predlozhenie/)[^/?#\s]+")
_SECRET_FIELD_MARKERS = ("TOKEN", "PASSWORD", "SECRET", "CREDENTIAL")


def redact_personal_offer_path(path: str) -> str:
    return _PERSONAL_OFFER_TOKEN_IN_PATH.sub(r"\g<1>[redacted]", path)


class _PersonalOfferAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn emits the request target as the third formatting argument.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, target, protocol, status = record.args
            if isinstance(target, str):
                record.args = (client, method, redact_personal_offer_path(target), protocol, status)
        return True


_PERSONAL_OFFER_ACCESS_LOG_FILTER = _PersonalOfferAccessLogFilter()


def mask_personal_offer_access_logs() -> None:
    logging.getLogger("uvicorn.access").addFilter(_PERSONAL_OFFER_ACCESS_LOG_FILTER)


def _configured_secret_values() -> tuple[str, ...]:
    values: list[str] = []
    for field_name in type(settings).model_fields:
        if not any(marker in field_name.upper() for marker in _SECRET_FIELD_MARKERS):
            continue
        value = str(getattr(settings, field_name, "") or "")
        if len(value) >= 8:
            values.append(value)
    return tuple(sorted(set(values), key=len, reverse=True))


def _strip_url_query(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    parsed = urlsplit(raw_url)
    if not parsed.query and not parsed.fragment:
        return raw_url
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _scrub_nested_value(value, secrets: tuple[str, ...]):
    if isinstance(value, str):
        scrubbed = _URL_IN_TEXT.sub(_strip_url_query, value)
        scrubbed = _TELEGRAM_TOKEN_IN_URL.sub("[redacted]", scrubbed)
        scrubbed = redact_personal_offer_path(scrubbed)
        for secret in secrets:
            scrubbed = scrubbed.replace(secret, "[redacted]")
        return scrubbed
    if isinstance(value, list):
        return [_scrub_nested_value(item, secrets) for item in value]
    if isinstance(value, dict):
        return {
            key: _scrub_nested_value(item, secrets)
            for key, item in value.items()
            if str(key).lower() not in {"http.query", "query_string"}
        }
    return value


def _scrub_sentry_event(event: dict, _hint: dict) -> dict:
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "query_string", "cookies", "headers", "env"):
            request.pop(key, None)

    exception = event.get("exception")
    if isinstance(exception, dict):
        values = exception.get("values")
        if isinstance(values, list):
            for value in values:
                if not isinstance(value, dict):
                    continue
                error_type = str(value.get("type") or "Exception")
                value["value"] = f"{error_type} message redacted"
                stacktrace = value.get("stacktrace")
                if isinstance(stacktrace, dict):
                    for frame in stacktrace.get("frames") or []:
                        if isinstance(frame, dict):
                            frame.pop("vars", None)
    return _scrub_nested_value(event, _configured_secret_values())


def init_sentry() -> None:
    if settings.SENTRY_DSN and settings.ENVIRONMENT != "test":
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
            environment=settings.ENVIRONMENT,
            send_default_pii=False,
            max_request_body_size="never",
            include_local_variables=False,
            before_send=_scrub_sentry_event,
            before_send_transaction=_scrub_sentry_event,
        )
