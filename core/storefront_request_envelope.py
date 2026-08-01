from __future__ import annotations

from collections.abc import Iterable


STOREFRONT_HEADER_PREFIX = b"x-mvn-storefront-"
STOREFRONT_SIGNING_HEADERS = frozenset(
    {
        b"x-mvn-storefront-key-id",
        b"x-mvn-storefront-host",
        b"x-mvn-storefront-timestamp",
        b"x-mvn-storefront-signature",
    }
)
PRIVATE_CACHE_CONTROL = "private, no-store"
PRIVATE_CDN_CACHE_CONTROL = "no-store"
STOREFRONT_VARY = "X-MVN-Storefront-Host"


def storefront_signing_header_state(
    raw_headers: Iterable[tuple[bytes, bytes]],
) -> tuple[bool, bool]:
    counts: dict[bytes, int] = {}
    for raw_name, _ in raw_headers:
        name = raw_name.lower()
        if not name.startswith(STOREFRONT_HEADER_PREFIX):
            continue
        counts[name] = counts.get(name, 0) + 1

    present = frozenset(counts)
    if not present:
        return False, False
    complete = (
        present == STOREFRONT_SIGNING_HEADERS
        and all(counts[name] == 1 for name in STOREFRONT_SIGNING_HEADERS)
    )
    return True, complete


def private_storefront_response_headers() -> dict[str, str]:
    return {
        "Cache-Control": PRIVATE_CACHE_CONTROL,
        "CDN-Cache-Control": PRIVATE_CDN_CACHE_CONTROL,
        "Vary": STOREFRONT_VARY,
    }


def force_private_storefront_response_headers(
    raw_headers: Iterable[tuple[bytes, bytes]],
) -> list[tuple[bytes, bytes]]:
    """Force private caching while preserving and de-duplicating Vary."""

    retained: list[tuple[bytes, bytes]] = []
    vary_tokens: list[str] = []
    seen_vary: set[str] = set()
    for name, value in raw_headers:
        normalized_name = name.lower()
        if normalized_name in {b"cache-control", b"cdn-cache-control"}:
            continue
        if normalized_name == b"vary":
            for item in value.decode("latin-1").split(","):
                token = item.strip()
                normalized_token = token.lower()
                if token and normalized_token not in seen_vary:
                    vary_tokens.append(token)
                    seen_vary.add(normalized_token)
            continue
        retained.append((name, value))

    if STOREFRONT_VARY.lower() not in seen_vary:
        vary_tokens.append(STOREFRONT_VARY)
    retained.extend(
        (
            (b"cache-control", PRIVATE_CACHE_CONTROL.encode("ascii")),
            (b"cdn-cache-control", PRIVATE_CDN_CACHE_CONTROL.encode("ascii")),
            (b"vary", ", ".join(vary_tokens).encode("latin-1")),
        )
    )
    return retained
