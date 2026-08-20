from __future__ import annotations

import ipaddress


class ClientAddressService:
    """Canonicalize the client address after trusted-proxy resolution."""

    UNAVAILABLE = "unavailable"

    @classmethod
    def normalize(cls, value: str | None) -> str:
        candidate = str(value or "").strip()
        if not candidate:
            return cls.UNAVAILABLE
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            return cls.UNAVAILABLE
        if isinstance(address, ipaddress.IPv6Address):
            return ipaddress.ip_network((address, 64), strict=False).with_prefixlen
        return address.compressed


__all__ = ["ClientAddressService"]
