"""Provider-neutral values returned by the advertising/search adapters.

The connection service owns persistence and encryption.  These types deliberately
contain no database concerns so adapters can be exercised with ``httpx.MockTransport``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping


class AnalyticsProviderError(ValueError):
    """A safe, stable error suitable for mapping to a public API response."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class AdvertisingSnapshot:
    provider: str
    period_start: date
    period_end: date
    impressions: int
    clicks: int
    spend: float
    conversions: float = 0.0
    currency: str | None = None

    @property
    def ctr(self) -> float:
        return round((self.clicks / self.impressions * 100) if self.impressions else 0.0, 2)


# Explicit names used by the dashboard integration.  Keep the shorter aliases
# for callers which already imported the first adapter-only revision.
AdvertisingProviderSnapshot = AdvertisingSnapshot


@dataclass(frozen=True)
class SearchQueryRow:
    query: str
    clicks: int
    impressions: int
    ctr: float
    position: float | None


@dataclass(frozen=True)
class SearchDemandProviderSnapshot:
    provider: str
    rows: tuple[SearchQueryRow, ...]

    @property
    def clicks(self) -> int:
        return sum(row.clicks for row in self.rows)

    @property
    def impressions(self) -> int:
        return sum(row.impressions for row in self.rows)


@dataclass(frozen=True)
class GoogleOAuthCredentialPayload:
    """JSON-ready OAuth credential shape; encryption is intentionally external."""

    access_token: str
    refresh_token: str | None
    client_id: str
    client_secret: str
    token_uri: str
    expiry: datetime | None
    scopes: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": "google_oauth_v1",
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "token_uri": self.token_uri,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "scopes": list(self.scopes),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "GoogleOAuthCredentialPayload":
        try:
            expiry_raw = payload.get("expiry")
            expiry = datetime.fromisoformat(expiry_raw) if isinstance(expiry_raw, str) else None
            scopes_raw = payload.get("scopes") or ()
            if not isinstance(scopes_raw, (list, tuple)):
                raise TypeError("scopes")
            return cls(
                access_token=str(payload["access_token"]),
                refresh_token=(str(payload["refresh_token"]) if payload.get("refresh_token") else None),
                client_id=str(payload["client_id"]),
                client_secret=str(payload["client_secret"]),
                token_uri=str(payload.get("token_uri") or "https://oauth2.googleapis.com/token"),
                expiry=expiry,
                scopes=tuple(str(scope) for scope in scopes_raw),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AnalyticsProviderError(
                "google_credentials_invalid", "Google connection needs to be connected again"
            ) from exc
