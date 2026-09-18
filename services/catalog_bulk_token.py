"""Signed, short-lived previews bind IDs, changes and actor without storing form data."""
import base64
import hashlib
import hmac
import json
import time

from core.config import settings


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()).hexdigest()


def sign_preview(payload: dict) -> str:
    value = {**payload, "expires": int(time.time()) + 900, "purpose": "catalog-bulk-v1"}
    encoded = base64.urlsafe_b64encode(json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")).encode()).decode()
    signature = hmac.new(settings.SECRET_KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def read_preview(token: str, actor: str) -> dict:
    try:
        encoded, signature = token.rsplit(".", 1)
        expected = hmac.new(settings.SECRET_KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(encoded))
        if payload["purpose"] != "catalog-bulk-v1" or payload["actor"] != actor or payload["expires"] <= time.time():
            raise ValueError()
        return payload
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Предпросмотр устарел или недействителен. Рассчитайте изменения заново.") from exc
