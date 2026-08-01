from __future__ import annotations


# These endpoints have independent trust contracts and intentionally do not
# select a tenant/storefront. Any expansion requires an explicit security review.
INTENTIONALLY_OPEN_PUBLIC_V1_REQUESTS = frozenset(
    {
        ("GET", "/api/v1/address-suggest"),
        ("GET", "/api/v1/feeds/yandex-business.yml"),
        ("GET", "/api/v1/proxy/bank"),
        ("GET", "/api/v1/proxy/egr"),
    }
)


def requires_storefront_gateway(*, method: str, path: str) -> bool:
    normalized_path = str(path or "")
    if not normalized_path.startswith("/api/v1/"):
        return False
    return (str(method or "").upper(), normalized_path) not in (
        INTENTIONALLY_OPEN_PUBLIC_V1_REQUESTS
    )
