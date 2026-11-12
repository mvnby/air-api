"""Exact procurement URL identities; never infer equality from tender text."""

import re
from urllib.parse import parse_qs, urlencode, urlsplit

GOS_KINDS = r"marketing|etrade|request|single-source|single-source-reference|limited"


def canonical_procurement_url(value: object) -> str | None:
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    value = value.strip()
    if "\\" in value or any(char.isspace() for char in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.username is not None or parsed.password is not None:
            return None
        if parsed.port not in {None, 80 if parsed.scheme == "http" else 443}:
            return None
        host = (parsed.hostname or "").lower().removeprefix("www.")
        path = parsed.path
        if host == "goszakupki.by" and re.fullmatch(rf"/({GOS_KINDS})/view/[1-9][0-9]*/?", path):
            return f"https://{host}{path.removesuffix('/')}"
        if host == "icetrade.by" and re.fullmatch(r"/tenders/all/view/[1-9][0-9]*/?", path):
            return f"https://{host}{path.removesuffix('/')}"
        if host == "zakupki.butb.by" and path == "/auctions/viewinvitation.html":
            values = parse_qs(parsed.query, keep_blank_values=True).get("auction", [])
            if len(values) == 1 and re.fullmatch(r"[A-Za-z0-9_-]+", values[0]):
                return f"https://{host}{path}?{urlencode({'auction': values[0]})}"
    except ValueError:
        pass
    return None


def canonical_tender_url(tender: dict) -> str | None:
    explicit = canonical_procurement_url(tender.get("canonical_url"))
    if explicit:
        return explicit
    # Derive identities only for native URLs belonging to that source. A GIAS
    # description/document URL is never an authoritative original reference.
    native = canonical_procurement_url(tender.get("url"))
    source = str(tender.get("source") or "").strip().casefold()
    if native and ((source in {"goszakupki", "goszakupki_by"} and "://goszakupki.by/" in native)
                   or (source in {"icetrade", "icetrade_by"} and "://icetrade.by/" in native)
                   or (source in {"butb", "butb_by"} and "://zakupki.butb.by/" in native)):
        return native
    return None


def original_native_identities(url: str) -> list[tuple[str, str]]:
    """Legacy original candidates, whose stored URLs must still be verified."""
    parsed = urlsplit(url)
    if parsed.hostname == "goszakupki.by":
        return [(source, parsed.path.rsplit("/", 1)[-1]) for source in ("goszakupki_by", "goszakupki")]
    if parsed.hostname == "icetrade.by":
        return [(source, parsed.path.rsplit("/", 1)[-1]) for source in ("icetrade_by", "icetrade")]
    if parsed.hostname == "zakupki.butb.by":
        return [(source, parse_qs(parsed.query)["auction"][0]) for source in ("butb_by", "butb")]
    return []
